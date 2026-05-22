from __future__ import annotations

import asyncio
import gc
import inspect
import json
import os
import sqlite3
import sys
import tracemalloc
from collections import OrderedDict
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated, Generator, Iterable, Iterator

import httpx
from fastapi import BackgroundTasks, FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse

try:
    import resource
except ImportError:  # pragma: no cover - unavailable on Windows
    resource = None

from config.logger import get_logger
from config.settings import DATA_PROVIDER, PAPER_STARTING_CASH, PROJECT_ROOT, TRADING_MODE
from monitoring.journal import initialise_journal
from utils.ticker_utils import to_data_provider_symbol, to_display_symbol


@asynccontextmanager
async def lifespan(app: FastAPI):
    _configure_uvloop()
    _set_memory_limits()
    _maybe_start_tracemalloc()
    app.state.quote_semaphore = asyncio.Semaphore(_MAX_CONCURRENT_REQUESTS)
    app.state.http_client = httpx.AsyncClient(timeout=httpx.Timeout(_HTTP_TIMEOUT_SECONDS))
    initialise_journal()  # ensures orders column exists in existing DBs
    try:
        yield
    finally:
        await app.state.http_client.aclose()


app = FastAPI(title="Trading Bot Web Dashboard", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

JOURNAL_PATH = PROJECT_ROOT / "logs" / "journal.db"
STATIC_INDEX = PROJECT_ROOT / "web_api" / "static" / "index.html"

logger = get_logger(__name__)
_HAS_LOGGED_ORDER_STRUCTURE = False
_GC_CHECK_INTERVAL_ROWS = 250
_MEMORY_LIMIT_MB = int(os.getenv("WEB_API_MEMORY_LIMIT_MB", "320"))
_GC_THRESHOLD_MB = int(os.getenv("WEB_API_GC_THRESHOLD_MB", "220"))
_TRACEMALLOC_ENABLED = os.getenv("WEB_API_ENABLE_TRACEMALLOC", "0") == "1"
_TRACEMALLOC_FRAMES = int(os.getenv("WEB_API_TRACEMALLOC_FRAMES", "15"))
_MAX_CONCURRENT_REQUESTS = int(os.getenv("WEB_API_MAX_CONCURRENT_REQUESTS", "4"))
_HTTP_TIMEOUT_SECONDS = float(os.getenv("WEB_API_HTTP_TIMEOUT_SECONDS", "8.0"))
_QUOTE_CACHE_SIZE = int(os.getenv("WEB_API_QUOTE_CACHE_SIZE", "512"))
_QUOTE_CACHE: OrderedDict[str, float | None] = OrderedDict()
_HISTORICAL_QUOTE_CACHE: OrderedDict[str, float | None] = OrderedDict()


def _configure_uvloop() -> None:
    if os.getenv("WEB_API_USE_UVLOOP", "0") != "1":
        return
    try:
        import uvloop  # type: ignore[import-not-found]

        asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
        logger.info("WEB_API | uvloop enabled")
    except Exception as exc:
        logger.warning("WEB_API | uvloop not enabled: %s", exc)


def _cache_get(cache: OrderedDict[str, float | None], key: str) -> float | None | object:
    value = cache.get(key, _CACHE_MISS)
    if value is _CACHE_MISS:
        return _CACHE_MISS
    cache.move_to_end(key)
    return value


def _cache_set(cache: OrderedDict[str, float | None], key: str, value: float | None) -> None:
    cache[key] = value
    cache.move_to_end(key)
    if len(cache) > _QUOTE_CACHE_SIZE:
        cache.popitem(last=False)


def _background_maintenance(processed_rows: int) -> None:
    _maybe_collect_garbage(processed_rows)


_CACHE_MISS = object()


def _ensure_runtime_clients(request: Request) -> tuple[httpx.AsyncClient, asyncio.Semaphore]:
    if not hasattr(request.app.state, "quote_semaphore"):
        request.app.state.quote_semaphore = asyncio.Semaphore(_MAX_CONCURRENT_REQUESTS)
    if not hasattr(request.app.state, "http_client"):
        request.app.state.http_client = httpx.AsyncClient(timeout=httpx.Timeout(_HTTP_TIMEOUT_SECONDS))
    return request.app.state.http_client, request.app.state.quote_semaphore


async def _await_if_needed(value: object) -> object:
    if inspect.isawaitable(value):
        return await value
    return value


def _get_memory_usage_mb() -> float | None:
    if resource is None:
        return None
    getrusage = getattr(resource, "getrusage", None)
    rusage_self = getattr(resource, "RUSAGE_SELF", None)
    if getrusage is None or rusage_self is None:
        return None
    usage = getrusage(rusage_self)
    rss = float(getattr(usage, "ru_maxrss", 0.0))
    if sys.platform == "darwin":
        return rss / (1024.0 * 1024.0)
    return rss / 1024.0


def _set_memory_limits() -> None:
    if resource is None:
        logger.info("WEB_API | resource module unavailable; memory limits disabled")
        return

    if _MEMORY_LIMIT_MB <= 0:
        logger.info("WEB_API | memory limit disabled (WEB_API_MEMORY_LIMIT_MB <= 0)")
        return

    getrlimit = getattr(resource, "getrlimit", None)
    setrlimit = getattr(resource, "setrlimit", None)
    if getrlimit is None or setrlimit is None:
        logger.warning("WEB_API | getrlimit/setrlimit unavailable; memory limits disabled")
        return

    soft_limit_bytes = _MEMORY_LIMIT_MB * 1024 * 1024
    for limit_name in ("RLIMIT_AS", "RLIMIT_DATA"):
        limit = getattr(resource, limit_name, None)
        if limit is None:
            continue
        try:
            _, current_hard = getrlimit(limit)
            target_soft = min(soft_limit_bytes, current_hard) if current_hard > 0 else soft_limit_bytes
            setrlimit(limit, (target_soft, current_hard))
            logger.info("WEB_API | set %s soft limit to %s MB", limit_name, target_soft // (1024 * 1024))
        except (ValueError, OSError) as exc:
            logger.warning("WEB_API | failed to set %s: %s", limit_name, exc)


def _maybe_collect_garbage(processed_rows: int) -> None:
    if processed_rows % _GC_CHECK_INTERVAL_ROWS != 0:
        return

    memory_mb = _get_memory_usage_mb()
    if memory_mb is None:
        return

    if memory_mb >= _GC_THRESHOLD_MB:
        collected = gc.collect()
        logger.info(
            "WEB_API | gc.collect() triggered at %.1fMB (threshold=%sMB), reclaimed=%s",
            memory_mb,
            _GC_THRESHOLD_MB,
            collected,
        )


def _maybe_start_tracemalloc() -> None:
    if not _TRACEMALLOC_ENABLED or tracemalloc.is_tracing():
        return
    tracemalloc.start(_TRACEMALLOC_FRAMES)
    logger.info("WEB_API | tracemalloc enabled (frames=%s)", _TRACEMALLOC_FRAMES)


async def _fetch_yahoo_chart(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    symbol: str,
    params: dict[str, str | int],
) -> dict | None:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    try:
        async with semaphore:
            response = await client.get(url, params=params)
        response.raise_for_status()
        payload = response.json()
        result = payload.get("chart", {}).get("result", [])
        if not result:
            return None
        return result[0]
    except Exception:
        return None


def _extract_close_points(result: dict) -> list[tuple[int, float]]:
    timestamps = result.get("timestamp") or []
    quote = (result.get("indicators") or {}).get("quote") or []
    closes = quote[0].get("close") if quote else []
    points: list[tuple[int, float]] = []
    for ts, close in zip(timestamps, closes):
        if close is None:
            continue
        try:
            points.append((int(ts), float(close)))
        except (TypeError, ValueError):
            continue
    return points


async def _fetch_historical_price(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    ticker: str,
    timestamp_minute: str,
) -> float | None:
    cache_key = f"hist:{ticker}:{timestamp_minute}"
    cached = _cache_get(_HISTORICAL_QUOTE_CACHE, cache_key)
    if cached is not _CACHE_MISS:
        return cached  # type: ignore[return-value]

    symbol = to_data_provider_symbol(ticker, DATA_PROVIDER)
    ts = _safe_parse_time(timestamp_minute).astimezone(timezone.utc)
    params: dict[str, str | int] = {
        "period1": int((ts - timedelta(minutes=10)).timestamp()),
        "period2": int((ts + timedelta(minutes=10)).timestamp()),
        "interval": "1m",
        "includePrePost": "false",
        "events": "div,split",
    }
    result = await _fetch_yahoo_chart(client, semaphore, symbol, params)
    if result is None:
        _cache_set(_HISTORICAL_QUOTE_CACHE, cache_key, None)
        return None

    points = _extract_close_points(result)
    if not points:
        _cache_set(_HISTORICAL_QUOTE_CACHE, cache_key, None)
        return None

    target_ts = int(ts.timestamp())
    nearest = min(points, key=lambda p: abs(p[0] - target_ts))[1]
    _cache_set(_HISTORICAL_QUOTE_CACHE, cache_key, nearest)
    return nearest


class JournalState:
    def __init__(self) -> None:
        self.mode = TRADING_MODE
        self.starting_cash = float(PAPER_STARTING_CASH)
        self.cash = float(PAPER_STARTING_CASH)
        self.max_trades: int | None = None
        self.max_cycles: int | None = None
        self.positions: dict[str, dict[str, float]] = {}
        self.trades: list[dict] = []
        self.cycles: list[dict] = []

    def reset(self) -> None:
        self.cash = self.starting_cash
        self.positions = {}
        self.trades = []
        self.cycles = []

    def append_trade(self, trade: dict) -> None:
        self.trades.append(trade)
        if self.max_trades is not None and len(self.trades) > self.max_trades:
            del self.trades[0]

    def append_cycle(self, cycle: dict) -> None:
        self.cycles.append(cycle)
        if self.max_cycles is not None and len(self.cycles) > self.max_cycles:
            del self.cycles[0]


def _safe_parse_time(ts: str | None) -> datetime:
    if not ts:
        return datetime.now(timezone.utc)
    try:
        parsed = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed
    except Exception:
        return datetime.now(timezone.utc)


def _display_ticker(ticker: str) -> str:
    return to_display_symbol(str(ticker or ""))


def _safe_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _normalize_timestamp(ts: str | None) -> str:
    return _safe_parse_time(ts).astimezone(timezone.utc).isoformat()


def _iter_cycle_rows(batch_size: int = 500) -> Iterator[sqlite3.Row]:
    if not JOURNAL_PATH.exists():
        return

    connection = sqlite3.connect(JOURNAL_PATH)
    try:
        connection.row_factory = sqlite3.Row
        cursor = connection.cursor()

        cursor.execute("PRAGMA table_info(cycles)")
        columns = {str(row[1]).lower() for row in cursor.fetchall()}

        if "orders" in columns:
            query = """
            SELECT id, timestamp, status, reason, free_cash, signals, orders, orders_executed, orders_approved
            FROM cycles
            ORDER BY id ASC
            """
        else:
            query = """
            SELECT id, timestamp, status, reason, free_cash, signals, NULL AS orders, orders_executed, orders_approved
            FROM cycles
            ORDER BY id ASC
            """

        cursor.execute(query)
        while True:
            rows = cursor.fetchmany(batch_size)
            if not rows:
                break
            for row in rows:
                yield row
    finally:
        connection.close()


def _apply_buy(state: JournalState, timestamp: str, ticker: str, shares: float, price: float) -> None:
    cost = round(shares * price, 6)
    pos = state.positions.get(ticker, {"shares": 0.0, "avg_cost": 0.0})
    old_shares = float(pos["shares"])
    old_avg = float(pos["avg_cost"])

    new_shares = round(old_shares + shares, 6)
    total_cost = (old_shares * old_avg) + cost
    new_avg = round(total_cost / new_shares, 6) if new_shares > 0 else 0.0

    state.positions[ticker] = {"shares": new_shares, "avg_cost": new_avg}
    state.cash = round(state.cash - cost, 6)

    state.append_trade(
        {
            "timestamp": timestamp,
            "ticker": ticker,
            "action": "BUY",
            "shares": shares,
            "price": price,
            "value": cost,
            "pnl": 0.0,
        }
    )


def _apply_sell(
    state: JournalState,
    timestamp: str,
    ticker: str,
    shares: float,
    price: float,
    pnl_override: float | None = None,
) -> None:
    pos = state.positions.get(ticker)
    if not pos:
        return

    held = float(pos["shares"])
    avg_cost = float(pos["avg_cost"])
    if held <= 0:
        return

    sell_shares = min(shares, held)
    proceeds = round(sell_shares * price, 6)
    realized_pnl = round((price - avg_cost) * sell_shares, 6)
    if pnl_override is not None:
        realized_pnl = round(float(pnl_override), 6)
    remaining = round(held - sell_shares, 6)

    if remaining <= 0:
        state.positions.pop(ticker, None)
    else:
        state.positions[ticker]["shares"] = remaining

    state.cash = round(state.cash + proceeds, 6)

    state.append_trade(
        {
            "timestamp": timestamp,
            "ticker": ticker,
            "action": "SELL",
            "shares": sell_shares,
            "price": price,
            "value": proceeds,
            "pnl": realized_pnl,
        }
    )


async def _parse_signal_payload(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    signal_payload: object,
    timestamp: str = "",
    ticker: str = "",
) -> tuple[str, float, float | None, float | None, bool]:
    signal = "HOLD"
    price = 0.0
    shares = None
    amount = None
    executed = False

    if isinstance(signal_payload, dict):
        signal = str(signal_payload.get("signal", "HOLD")).upper()
        price = float(_safe_float(signal_payload.get("price")) or 0.0)
        shares = _safe_float(signal_payload.get("shares"))
        amount = _safe_float(signal_payload.get("amount"))
        executed = bool(signal_payload.get("executed", False))
    elif isinstance(signal_payload, str):
        signal = signal_payload.upper()
        # Legacy plain-string signal — recover price with async Yahoo call.
        if signal in {"BUY", "SELL"} and ticker and timestamp:
            historical = await _fetch_historical_price(client, semaphore, ticker, timestamp[:16])
            if historical is not None:
                price = historical

    return signal, price, shares, amount, executed


def _apply_signal_trade(
    state: JournalState,
    timestamp: str,
    ticker: str,
    signal: str,
    price: float,
    shares: float | None,
    amount: float | None,
) -> None:
    if signal == "BUY":
        effective_shares = shares
        if effective_shares is None and amount is not None and price > 0:
            effective_shares = round(amount / price, 6)
        if effective_shares is None or effective_shares <= 0:
            return
        _apply_buy(state, timestamp, ticker, effective_shares, price)
        return

    effective_shares = shares
    if effective_shares is None or effective_shares <= 0:
        pos = state.positions.get(ticker)
        effective_shares = float(pos["shares"]) if pos else 0.0
    if effective_shares <= 0:
        return
    _apply_sell(state, timestamp, ticker, effective_shares, price)


def _estimate_cash_delta_per_trade(
    resolved: list[tuple[str, str, float, float | None, float | None, bool]],
    orders_executed: int,
    cash_before: float | None,
    cash_after: float | None,
) -> float | None:
    n_buy = sum(1 for _, sig, *_ in resolved if sig == "BUY")
    n_sell = sum(1 for _, sig, *_ in resolved if sig == "SELL")
    if not ((n_buy > 0) ^ (n_sell > 0)):  # must be pure-direction
        return None
    if cash_before is None or cash_after is None or orders_executed <= 0:
        return None
    total_delta = abs(cash_after - cash_before)
    return round(total_delta / orders_executed, 6) if total_delta > 0 else None


def _apply_resolved_signal(
    state: JournalState,
    timestamp: str,
    ticker: str,
    signal: str,
    price: float,
    shares: float | None,
    amount: float | None,
    executed: bool,
    remaining: list[int],  # mutable single-element list
    cash_delta_per_trade: float | None,
) -> None:
    if not executed and remaining[0] > 0:
        executed = True
        remaining[0] -= 1

    if not executed or price <= 0:
        return

    effective_amount = amount
    if shares is None and effective_amount is None:
        effective_amount = cash_delta_per_trade

    _apply_signal_trade(state, timestamp, ticker, signal, price, shares, effective_amount)


async def _process_signals_into_trades(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    state: JournalState,
    timestamp: str,
    signals: dict,
    orders_executed: int,
    cash_before: float | None = None,
    cash_after: float | None = None,
) -> None:
    resolved: list[tuple[str, str, float, float | None, float | None, bool]] = []
    for ticker, payload in signals.items():
        sig, price, shares, amount, executed = await _parse_signal_payload(
            client,
            semaphore,
            payload,
            timestamp=timestamp,
            ticker=ticker,
        )
        if sig in {"BUY", "SELL"}:
            resolved.append((ticker, sig, price, shares, amount, executed))

    cash_delta_per_trade = _estimate_cash_delta_per_trade(
        resolved, orders_executed, cash_before, cash_after
    )
    remaining = [int(orders_executed or 0)]

    for ticker, signal, price, shares, amount, executed in resolved:
        _apply_resolved_signal(
            state, timestamp, ticker, signal, price,
            shares, amount, executed, remaining, cash_delta_per_trade,
        )


def _extract_action(order: dict) -> str | None:
    action = str(order.get("action") or order.get("side") or order.get("signal") or "").upper()
    if action in {"BUY", "SELL"}:
        return action
    if order.get("proceeds") is not None:
        return "SELL"
    if any(order.get(k) is not None for k in ("cost", "value", "amount")):
        return "BUY"
    return None


def _extract_buy_amount(order: dict) -> float | None:
    for key in ("cost", "value", "amount"):
        value = _safe_float(order.get(key))
        if value is not None and value > 0:
            return value
    return None


def _extract_shares(order: dict) -> float | None:
    for key in ("shares", "quantity"):
        value = _safe_float(order.get(key))
        if value is not None and value > 0:
            return value
    return None


def _extract_price(order: dict, shares: float | None, amount: float | None) -> float | None:
    explicit = _safe_float(order.get("price"))
    if explicit is not None and explicit > 0:
        return explicit
    if shares is not None and shares > 0 and amount is not None and amount > 0:
        return round(amount / shares, 6)
    proceeds = _safe_float(order.get("proceeds"))
    if shares is not None and shares > 0 and proceeds is not None and proceeds > 0:
        return round(proceeds / shares, 6)
    return None


def _apply_buy_order(state: JournalState, timestamp: str, ticker: str, order: dict) -> bool:
    shares = _extract_shares(order)
    amount = _extract_buy_amount(order)
    price = _extract_price(order, shares, amount)
    if price is None or price <= 0:
        return False
    if shares is None and amount is not None:
        shares = round(amount / price, 6)
    if shares is None or shares <= 0:
        return False
    _apply_buy(state, timestamp, ticker, shares, price)
    return True


def _apply_sell_order(state: JournalState, timestamp: str, ticker: str, order: dict) -> bool:
    shares = _extract_shares(order)
    if shares is None or shares <= 0:
        pos = state.positions.get(ticker)
        shares = float(pos["shares"]) if pos else 0.0
    if shares <= 0:
        return False

    proceeds = _safe_float(order.get("proceeds"))
    price = _extract_price(order, shares, proceeds)
    if price is None or price <= 0:
        return False

    pnl_override = None
    cost_basis = _safe_float(order.get("cost_basis"))
    if proceeds is not None and cost_basis is not None:
        pnl_override = proceeds - cost_basis

    _apply_sell(state, timestamp, ticker, shares, price, pnl_override=pnl_override)
    return True


def _process_orders_into_trades(state: JournalState, timestamp: str, orders: list[dict]) -> None:
    for order in orders:
        if not isinstance(order, dict) or not bool(order.get("executed", True)):
            continue

        ticker = str(order.get("ticker") or "").strip()
        action = _extract_action(order)
        if not ticker or action not in {"BUY", "SELL"}:
            continue

        if action == "BUY":
            _apply_buy_order(state, timestamp, ticker, order)
        else:
            _apply_sell_order(state, timestamp, ticker, order)


def _parse_orders_from_row(row: sqlite3.Row) -> list[dict]:
    orders_raw = row["orders"] if "orders" in row.keys() else None
    if not orders_raw:
        return []
    try:
        parsed_orders = json.loads(orders_raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed_orders, list):
        return []
    return [order for order in parsed_orders if isinstance(order, dict)]


def _parse_signals_from_row(row: sqlite3.Row) -> dict:
    try:
        return json.loads(row["signals"]) if row["signals"] else {}
    except json.JSONDecodeError:
        return {}


def _log_first_order_structure(rows: list[sqlite3.Row]) -> None:
    global _HAS_LOGGED_ORDER_STRUCTURE
    if _HAS_LOGGED_ORDER_STRUCTURE:
        return

    for row in rows:
        orders = _parse_orders_from_row(row)
        if not orders:
            continue
        logger.info("WEB_API | first order keys detected: %s", sorted(orders[0].keys()))
        _HAS_LOGGED_ORDER_STRUCTURE = True
        return

    _HAS_LOGGED_ORDER_STRUCTURE = True


async def _fetch_current_price_for_ticker(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    ticker: str,
) -> float | None:
    cache_key = f"cur:{ticker}"
    cached = _cache_get(_QUOTE_CACHE, cache_key)
    if cached is not _CACHE_MISS:
        return cached  # type: ignore[return-value]

    symbol = to_data_provider_symbol(ticker, DATA_PROVIDER)
    params: dict[str, str | int] = {
        "range": "1d",
        "interval": "1m",
        "includePrePost": "false",
        "events": "div,split",
    }
    result = await _fetch_yahoo_chart(client, semaphore, symbol, params)
    if result is None:
        _cache_set(_QUOTE_CACHE, cache_key, None)
        return None

    points = _extract_close_points(result)
    if not points:
        _cache_set(_QUOTE_CACHE, cache_key, None)
        return None

    latest_price = points[-1][1]
    _cache_set(_QUOTE_CACHE, cache_key, latest_price)
    return latest_price


async def _fetch_current_prices(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    tickers: list[str],
) -> dict[str, float]:
    prices: dict[str, float] = {}

    async def _fetch_one(ticker: str) -> tuple[str, float | None]:
        return ticker, await _fetch_current_price_for_ticker(client, semaphore, ticker)

    results = await asyncio.gather(*(_fetch_one(ticker) for ticker in tickers), return_exceptions=True)
    for result in results:
        if isinstance(result, BaseException):
            continue
        ticker, price = result
        if price is not None:
            prices[ticker] = price
    return prices


def _append_cycle(state: JournalState, row: sqlite3.Row, timestamp: str, signals: dict) -> None:
    state.append_cycle(
        {
            "id": int(row["id"]),
            "timestamp": timestamp,
            "status": row["status"],
            "reason": row["reason"],
            "orders_executed": int(row["orders_executed"] or 0),
            "orders_approved": int(row["orders_approved"] or 0),
            "free_cash": float(state.cash),
            "signals": signals,
        }
    )


async def reconstruct_state(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    max_trades: int | None = None,
    max_cycles: int | None = None,
) -> JournalState:
    global _HAS_LOGGED_ORDER_STRUCTURE

    state = JournalState()
    state.reset()
    state.max_trades = max_trades
    state.max_cycles = max_cycles

    processed_rows = 0
    for row in _iter_cycle_rows():
        processed_rows += 1
        timestamp = _normalize_timestamp(row["timestamp"])
        orders_executed = int(row["orders_executed"] or 0)
        signals = _parse_signals_from_row(row)
        orders = _parse_orders_from_row(row)

        if not _HAS_LOGGED_ORDER_STRUCTURE and orders:
            logger.info("WEB_API | first order keys detected: %s", sorted(orders[0].keys()))
            _HAS_LOGGED_ORDER_STRUCTURE = True

        cash_before = float(state.cash)
        if row["free_cash"] is not None:
            cash_after = float(row["free_cash"])
        else:
            cash_after = cash_before

        if orders:
            _process_orders_into_trades(state, timestamp, orders)
        else:
            await _process_signals_into_trades(
                client,
                semaphore,
                state, timestamp, signals, orders_executed,
                cash_before=cash_before, cash_after=cash_after,
            )

        state.cash = cash_after
        _append_cycle(state, row, timestamp, signals)
        _maybe_collect_garbage(processed_rows)
        if processed_rows % 200 == 0:
            await asyncio.sleep(0.01)

    if not _HAS_LOGGED_ORDER_STRUCTURE:
        _HAS_LOGGED_ORDER_STRUCTURE = True

    return state


def _compute_position_rows(state: JournalState, prices: dict[str, float]) -> list[dict]:
    rows: list[dict] = []
    for ticker, pos in state.positions.items():
        shares = float(pos["shares"])
        avg_cost = float(pos["avg_cost"])
        current_price = float(prices.get(ticker, avg_cost))
        pnl = (current_price - avg_cost) * shares
        cost_basis = avg_cost * shares
        pnl_percent = (pnl / cost_basis * 100.0) if cost_basis > 0 else 0.0
        rows.append(
            {
                "ticker": _display_ticker(ticker),
                "shares": shares,
                "avg_cost": avg_cost,
                "current_price": current_price,
                "pnl": pnl,
                "pnl_percent": pnl_percent,
            }
        )
    return rows


def _today_pnl(state: JournalState) -> float:
    today = datetime.now(timezone.utc).date()
    pnl = 0.0
    for trade in state.trades:
        ts = _safe_parse_time(trade.get("timestamp"))
        if ts.date() == today and trade.get("action") == "SELL":
            pnl += float(trade.get("pnl", 0.0))
    return pnl


def _iter_json_array_chunks(items: Iterable[dict]) -> Generator[str, None, None]:
    yield "["
    first = True
    for item in items:
        if not first:
            yield ","
        else:
            first = False
        yield json.dumps(item, separators=(",", ":"), ensure_ascii=True)
    yield "]"


def _iter_recent_trades(state: JournalState, limit: int) -> Iterator[dict]:
    for trade in reversed(state.trades[-limit:]):
        shares = _safe_float(trade.get("shares")) or 0.0
        price = _safe_float(trade.get("price")) or 0.0
        value = _safe_float(trade.get("value"))
        if value is None:
            value = round(shares * price, 6)

        yield {
            **trade,
            "value": value,
            "timestamp": _normalize_timestamp(trade.get("timestamp")),
            "ticker": _display_ticker(str(trade.get("ticker", ""))),
        }


def _iter_recent_cycles(state: JournalState, limit: int) -> Iterator[dict]:
    for cycle in reversed(state.cycles[-limit:]):
        yield {
            "timestamp": cycle["timestamp"],
            "orders_executed": cycle["orders_executed"],
            "free_cash": cycle["free_cash"],
        }


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_INDEX)


@app.get("/api/state")
async def api_state(request: Request, background_tasks: BackgroundTasks) -> dict:
    client, semaphore = _ensure_runtime_clients(request)
    state = await reconstruct_state(client, semaphore, max_trades=2000, max_cycles=5000)
    prices_result = _fetch_current_prices(client, semaphore, list(state.positions.keys()))
    prices = await _await_if_needed(prices_result)
    prices = prices if isinstance(prices, dict) else {}
    position_rows = _compute_position_rows(state, prices)
    market_value = sum((row["current_price"] * row["shares"]) for row in position_rows)
    unrealized = sum(row["pnl"] for row in position_rows)
    background_tasks.add_task(_background_maintenance, len(state.cycles))

    return {
        "mode": state.mode,
        "cash": float(state.cash),
        "positions_count": len(state.positions),
        "portfolio_value": float(state.cash + market_value),
        "unrealized_pnl": float(unrealized),
        "today_pnl": float(_today_pnl(state)),
        "kill_switch_active": any(
            cycle.get("reason") == "kill_switch_active" for cycle in state.cycles[-20:]
        ),
    }


@app.get("/api/positions")
async def api_positions(request: Request, background_tasks: BackgroundTasks) -> list[dict]:
    client, semaphore = _ensure_runtime_clients(request)
    state = await reconstruct_state(client, semaphore, max_cycles=2000)
    prices_result = _fetch_current_prices(client, semaphore, list(state.positions.keys()))
    prices = await _await_if_needed(prices_result)
    prices = prices if isinstance(prices, dict) else {}
    background_tasks.add_task(_background_maintenance, len(state.cycles))
    return _compute_position_rows(state, prices)


@app.get("/api/trades")
async def api_trades(
    request: Request,
    background_tasks: BackgroundTasks,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
) -> StreamingResponse:
    client, semaphore = _ensure_runtime_clients(request)
    state = await reconstruct_state(client, semaphore, max_trades=max(limit * 20, 1000), max_cycles=3000)
    background_tasks.add_task(_background_maintenance, len(state.cycles))
    return StreamingResponse(
        _iter_json_array_chunks(_iter_recent_trades(state, limit)),
        media_type="application/json",
    )


@app.get("/api/equity_history")
async def api_equity_history(request: Request, background_tasks: BackgroundTasks) -> dict:
    client, semaphore = _ensure_runtime_clients(request)
    state = await reconstruct_state(client, semaphore, max_cycles=10000)
    cycles = state.cycles
    if not cycles:
        return {"timestamps": [], "values": []}

    threshold = datetime.now(timezone.utc) - timedelta(days=30)
    filtered = [c for c in cycles if _safe_parse_time(c.get("timestamp")) >= threshold]
    if not filtered:
        filtered = cycles

    filtered = filtered[-100:]
    timestamps = [c["timestamp"] for c in filtered]
    values = [float(c.get("free_cash", 0.0)) for c in filtered]
    background_tasks.add_task(_background_maintenance, len(state.cycles))

    return {"timestamps": timestamps, "values": values}


@app.get("/api/cycle_history")
async def api_cycle_history(
    request: Request,
    background_tasks: BackgroundTasks,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
) -> StreamingResponse:
    client, semaphore = _ensure_runtime_clients(request)
    state = await reconstruct_state(client, semaphore, max_cycles=max(limit * 20, 2000), max_trades=1000)
    background_tasks.add_task(_background_maintenance, len(state.cycles))
    return StreamingResponse(
        _iter_json_array_chunks(_iter_recent_cycles(state, limit)),
        media_type="application/json",
    )


@app.get("/api/debug/memory")
def api_debug_memory(limit: Annotated[int, Query(ge=1, le=30)] = 10) -> dict:
    """Expose tracemalloc snapshots to identify top allocation lines."""
    if not tracemalloc.is_tracing():
        tracemalloc.start(_TRACEMALLOC_FRAMES)

    current, peak = tracemalloc.get_traced_memory()
    snapshot = tracemalloc.take_snapshot()
    top_stats = snapshot.statistics("lineno")[:limit]
    memory_mb = _get_memory_usage_mb()

    return {
        "rss_mb": round(memory_mb, 2) if memory_mb is not None else None,
        "tracemalloc_current_mb": round(current / (1024 * 1024), 3),
        "tracemalloc_peak_mb": round(peak / (1024 * 1024), 3),
        "top_allocations": [
            {
                "location": str(stat.traceback[0]),
                "size_kb": round(stat.size / 1024, 2),
                "count": stat.count,
            }
            for stat in top_stats
        ],
        "notes": [
            "Set WEB_API_ENABLE_TRACEMALLOC=1 to start tracing on app startup.",
            "Call this endpoint while traffic is active for useful snapshots.",
        ],
    }
