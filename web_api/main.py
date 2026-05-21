from __future__ import annotations

import json
import sqlite3
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated

import yfinance as yf
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from config.logger import get_logger
from config.settings import DATA_PROVIDER, PAPER_STARTING_CASH, PROJECT_ROOT, TRADING_MODE
from monitoring.journal import initialise_journal
from utils.ticker_utils import to_data_provider_symbol, to_display_symbol


@asynccontextmanager
async def lifespan(app: FastAPI):
    initialise_journal()  # ensures orders column exists in existing DBs
    yield


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
_HISTORICAL_PRICE_CACHE: dict[tuple[str, str], float | None] = {}


def _fetch_historical_price(ticker: str, timestamp: str) -> float | None:
    """Return the closing price nearest to *timestamp* from yfinance (1-min bars).
    Results are cached in-process so a single reconstruction pass is cheap.
    """
    symbol = to_data_provider_symbol(ticker, DATA_PROVIDER)
    key = (symbol, timestamp[:16])  # cache at minute granularity
    if key in _HISTORICAL_PRICE_CACHE:
        return _HISTORICAL_PRICE_CACHE[key]

    ts = _safe_parse_time(timestamp)
    start = (ts - timedelta(minutes=5)).strftime("%Y-%m-%d")
    end = (ts + timedelta(minutes=10)).strftime("%Y-%m-%d")
    try:
        hist = yf.Ticker(symbol).history(start=start, end=end, interval="1m")
        if hist.empty:
            _HISTORICAL_PRICE_CACHE[key] = None
            return None
        if hist.index.tzinfo is None:
            hist.index = hist.index.tz_localize("UTC")
        else:
            hist.index = hist.index.tz_convert("UTC")
        diffs = abs(hist.index - ts)
        price = float(hist["Close"].iloc[diffs.argmin()])
        _HISTORICAL_PRICE_CACHE[key] = price
        return price
    except Exception:
        _HISTORICAL_PRICE_CACHE[key] = None
        return None


class JournalState:
    def __init__(self) -> None:
        self.mode = TRADING_MODE
        self.starting_cash = float(PAPER_STARTING_CASH)
        self.cash = float(PAPER_STARTING_CASH)
        self.positions: dict[str, dict[str, float]] = {}
        self.trades: list[dict] = []
        self.cycles: list[dict] = []

    def reset(self) -> None:
        self.cash = self.starting_cash
        self.positions = {}
        self.trades = []
        self.cycles = []


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
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_timestamp(ts: str | None) -> str:
    return _safe_parse_time(ts).astimezone(timezone.utc).isoformat()


def _load_cycle_rows() -> list[sqlite3.Row]:
    if not JOURNAL_PATH.exists():
        return []

    connection = sqlite3.connect(JOURNAL_PATH)
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
    rows = cursor.fetchall()
    connection.close()
    return rows


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

    state.trades.append(
        {
            "timestamp": timestamp,
            "ticker": ticker,
            "action": "BUY",
            "shares": shares,
            "price": price,
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

    state.trades.append(
        {
            "timestamp": timestamp,
            "ticker": ticker,
            "action": "SELL",
            "shares": sell_shares,
            "price": price,
            "pnl": realized_pnl,
        }
    )


def _parse_signal_payload(
    signal_payload: object, timestamp: str = "", ticker: str = ""
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
        # Legacy plain-string signal — try to recover price from yfinance history.
        if signal in {"BUY", "SELL"} and ticker and timestamp:
            historical = _fetch_historical_price(ticker, timestamp)
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


def _process_signals_into_trades(
    state: JournalState,
    timestamp: str,
    signals: dict,
    orders_executed: int,
    cash_before: float | None = None,
    cash_after: float | None = None,
) -> None:
    resolved = [
        (ticker, sig, price, shares, amount, executed)
        for ticker, payload in signals.items()
        for sig, price, shares, amount, executed in [
            _parse_signal_payload(payload, timestamp=timestamp, ticker=ticker)
        ]
        if sig in {"BUY", "SELL"}
    ]

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


def _fetch_current_prices(tickers: list[str]) -> dict[str, float]:
    prices: dict[str, float] = {}
    for ticker in tickers:
        symbol = to_data_provider_symbol(ticker, DATA_PROVIDER)
        try:
            hist = yf.Ticker(symbol).history(period="1d", interval="1m")
            if not hist.empty:
                prices[ticker] = float(hist["Close"].iloc[-1])
        except Exception:
            continue
    return prices


def _append_cycle(state: JournalState, row: sqlite3.Row, timestamp: str, signals: dict) -> None:
    state.cycles.append(
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


def reconstruct_state() -> JournalState:
    state = JournalState()
    state.reset()
    rows = _load_cycle_rows()
    _log_first_order_structure(rows)

    for row in rows:
        timestamp = _normalize_timestamp(row["timestamp"])
        orders_executed = int(row["orders_executed"] or 0)
        signals = _parse_signals_from_row(row)
        orders = _parse_orders_from_row(row)

        cash_before = float(state.cash)
        if row["free_cash"] is not None:
            cash_after = float(row["free_cash"])
        else:
            cash_after = cash_before

        if orders:
            _process_orders_into_trades(state, timestamp, orders)
        else:
            _process_signals_into_trades(
                state, timestamp, signals, orders_executed,
                cash_before=cash_before, cash_after=cash_after,
            )

        state.cash = cash_after
        _append_cycle(state, row, timestamp, signals)

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


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_INDEX)


@app.get("/api/state")
def api_state() -> dict:
    state = reconstruct_state()
    prices = _fetch_current_prices(list(state.positions.keys()))
    position_rows = _compute_position_rows(state, prices)
    market_value = sum((row["current_price"] * row["shares"]) for row in position_rows)
    unrealized = sum(row["pnl"] for row in position_rows)

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
def api_positions() -> list[dict]:
    state = reconstruct_state()
    prices = _fetch_current_prices(list(state.positions.keys()))
    return _compute_position_rows(state, prices)


@app.get("/api/trades")
def api_trades(limit: Annotated[int, Query(ge=1, le=500)] = 50) -> list[dict]:
    state = reconstruct_state()
    trades = state.trades[-limit:][::-1]
    return [
        {
            **trade,
            "timestamp": _normalize_timestamp(trade.get("timestamp")),
            "ticker": _display_ticker(str(trade.get("ticker", ""))),
        }
        for trade in trades
    ]


@app.get("/api/equity_history")
def api_equity_history() -> dict:
    state = reconstruct_state()
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

    return {"timestamps": timestamps, "values": values}


@app.get("/api/cycle_history")
def api_cycle_history() -> list[dict]:
    state = reconstruct_state()
    return [
        {
            "timestamp": c["timestamp"],
            "orders_executed": c["orders_executed"],
            "free_cash": c["free_cash"],
        }
        for c in state.cycles[-100:][::-1]
    ]
