from __future__ import annotations

import argparse
import math
from pathlib import Path

import pandas as pd
import yfinance as yf

from utils.ticker_utils import to_data_provider_symbol

SLIPPAGE = 0.0001  # 0.01%
RISK_PER_TRADE = 0.01  # 1%
ANNUAL_BARS_5M = 252 * 78


def _period_to_days(period: str) -> int | None:
    if not period:
        return None
    p = period.strip().lower()
    suffix_map = {
        "d": 1,
        "wk": 7,
        "mo": 30,
        "y": 365,
    }
    for suffix, multiplier in suffix_map.items():
        if p.endswith(suffix):
            value = p[: -len(suffix)]
            if not value.isdigit():
                return None
            return int(value) * multiplier
    return None


def _download_history(symbol: str, period: str, interval: str) -> pd.DataFrame:
    provider_symbol = to_data_provider_symbol(symbol, "yahoo")
    return yf.Ticker(provider_symbol).history(period=period, interval=interval, auto_adjust=False)


def fetch_ohlcv(
    symbol: str,
    period: str = "6mo",
    interval: str = "5m",
    force_interval: bool = False,
) -> pd.DataFrame:
    requested_period = period
    requested_interval = interval
    clamped_period = period

    days = _period_to_days(period)
    if interval in {"5m", "15m", "30m"} and days is not None and days > 60:
        clamped_period = "60d"
        print(
            f"Interval {interval} limited to 60 days by Yahoo. "
            f"Using last 60 days instead of {requested_period}."
        )

    attempts: list[tuple[str, str]] = [(clamped_period, requested_interval)]
    if not force_interval:
        if requested_interval != "60m":
            attempts.append((requested_period, "60m"))
        if requested_interval != "1d":
            attempts.append((requested_period, "1d"))

    raw = pd.DataFrame()
    used_period = clamped_period
    used_interval = requested_interval
    for attempt_period, attempt_interval in attempts:
        raw = _download_history(symbol=symbol, period=attempt_period, interval=attempt_interval)
        used_period = attempt_period
        used_interval = attempt_interval
        if not raw.empty:
            break

    if raw.empty:
        attempts_text = ", ".join([f"{p}/{i}" for p, i in attempts])
        raise RuntimeError(
            f"No market data returned for {symbol} after trying: {attempts_text}"
        )

    data = raw.rename(
        columns={
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "volume",
        }
    )
    data = data[["open", "high", "low", "close", "volume"]].copy()
    data.index = pd.to_datetime(data.index, utc=True)
    data = data.dropna(subset=["open", "high", "low", "close", "volume"])
    data.attrs["used_period"] = used_period
    data.attrs["used_interval"] = used_interval
    return data


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    data = df.copy()

    delta = data["close"].diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / 14, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / 14, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, pd.NA)
    data["rsi_14"] = 100 - (100 / (1 + rs))
    data["rsi_14"] = data["rsi_14"].fillna(50.0)

    typical_price = (data["high"] + data["low"] + data["close"]) / 3.0
    cumulative_tpv = (typical_price * data["volume"]).cumsum()
    cumulative_volume = data["volume"].cumsum().replace(0, pd.NA)
    data["vwap"] = (cumulative_tpv / cumulative_volume).fillna(data["close"])

    return data


def generate_signal_from_row(close: float, rsi_14: float, vwap: float) -> str:
    if close < vwap and rsi_14 < 40:
        return "BUY"
    if close > vwap and rsi_14 > 60:
        return "SELL"
    return "HOLD"


def _trade_amount(signal: str, cash: float) -> float:
    if signal == "HOLD" or cash <= 0:
        return 0.0
    amount = round(cash * RISK_PER_TRADE, 2)
    if amount < 1.0:
        return 0.0
    return amount


def _sharpe_ratio(equity_curve: pd.Series, interval: str) -> float:
    returns = equity_curve.pct_change().dropna()
    if returns.empty:
        return 0.0

    std = returns.std(ddof=0)
    if std == 0 or math.isnan(std):
        return 0.0

    if interval == "5m":
        periods = ANNUAL_BARS_5M
    else:
        periods = max(len(returns), 1)

    return float((returns.mean() / std) * math.sqrt(periods))


def calculate_metrics(
    equity_curve: pd.Series,
    closed_trade_pnls: list[float],
    initial_capital: float,
    interval: str = "5m",
) -> dict:
    if equity_curve.empty:
        return {
            "total_return_pct": 0.0,
            "sharpe_ratio": 0.0,
            "max_drawdown_pct": 0.0,
            "win_rate_pct": 0.0,
            "profit_factor": 0.0,
            "number_of_trades": 0,
        }

    ending_equity = float(equity_curve.iloc[-1])
    if initial_capital > 0:
        total_return_pct = ((ending_equity / initial_capital) - 1.0) * 100.0
    else:
        total_return_pct = 0.0

    rolling_peak = equity_curve.cummax()
    drawdown = (rolling_peak - equity_curve) / rolling_peak.replace(0, pd.NA)
    max_drawdown_pct = float(drawdown.fillna(0.0).max() * 100.0)

    trade_count = len(closed_trade_pnls)
    wins = [p for p in closed_trade_pnls if p > 0]
    losses = [p for p in closed_trade_pnls if p < 0]
    win_rate_pct = (len(wins) / trade_count * 100.0) if trade_count > 0 else 0.0

    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    if gross_loss == 0:
        profit_factor = float("inf") if gross_profit > 0 else 0.0
    else:
        profit_factor = gross_profit / gross_loss

    sharpe = _sharpe_ratio(equity_curve, interval=interval)

    return {
        "total_return_pct": float(total_return_pct),
        "sharpe_ratio": float(sharpe),
        "max_drawdown_pct": float(max_drawdown_pct),
        "win_rate_pct": float(win_rate_pct),
        "profit_factor": float(profit_factor),
        "number_of_trades": trade_count,
    }


def _execute_buy(
    cash: float,
    shares: float,
    avg_cost: float,
    next_open: float,
    signal: str,
    timestamp: pd.Timestamp,
    trade_log: list[dict],
) -> tuple[float, float, float]:
    amount = _trade_amount(signal, cash)
    if amount <= 0:
        return cash, shares, avg_cost

    fill_price = next_open * (1.0 + SLIPPAGE)
    buy_shares = amount / fill_price
    if buy_shares <= 0:
        return cash, shares, avg_cost

    total_cost_before = shares * avg_cost
    total_cost_after = total_cost_before + amount
    new_shares = shares + buy_shares
    new_avg = total_cost_after / new_shares if new_shares > 0 else 0.0
    new_cash = round(cash - amount, 6)

    trade_log.append(
        {
            "timestamp": timestamp.isoformat(),
            "action": "BUY",
            "shares": float(buy_shares),
            "price": float(fill_price),
            "value": float(amount),
            "pnl": 0.0,
        }
    )
    return new_cash, new_shares, new_avg


def _execute_sell(
    cash: float,
    shares: float,
    avg_cost: float,
    next_open: float,
    timestamp: pd.Timestamp,
    trade_log: list[dict],
    closed_trade_pnls: list[float],
) -> tuple[float, float, float]:
    if shares <= 0:
        return cash, shares, avg_cost

    fill_price = next_open * (1.0 - SLIPPAGE)
    proceeds = shares * fill_price
    cost_basis = shares * avg_cost
    pnl = proceeds - cost_basis
    new_cash = round(cash + proceeds, 6)

    trade_log.append(
        {
            "timestamp": timestamp.isoformat(),
            "action": "SELL",
            "shares": float(shares),
            "price": float(fill_price),
            "value": float(proceeds),
            "pnl": float(pnl),
        }
    )
    closed_trade_pnls.append(float(pnl))
    return new_cash, 0.0, 0.0


def simulate_backtest(
    df: pd.DataFrame,
    initial_capital: float = 1000.0,
    interval: str = "5m",
) -> tuple[pd.DataFrame, list[dict], dict]:
    if df.empty:
        empty_equity = pd.DataFrame(columns=["timestamp", "equity"])
        return empty_equity, [], {
            "total_return_pct": 0.0,
            "sharpe_ratio": 0.0,
            "max_drawdown_pct": 0.0,
            "win_rate_pct": 0.0,
            "profit_factor": 0.0,
            "number_of_trades": 0,
        }

    data = add_indicators(df)

    cash = float(initial_capital)
    shares = 0.0
    avg_cost = 0.0
    trade_log: list[dict] = []
    closed_trade_pnls: list[float] = []
    equity_points: list[dict] = []

    for i in range(len(data) - 1):
        row = data.iloc[i]
        next_open = float(data.iloc[i + 1]["open"])
        timestamp = data.index[i]

        signal = generate_signal_from_row(float(row["close"]), float(row["rsi_14"]), float(row["vwap"]))

        if signal == "BUY":
            cash, shares, avg_cost = _execute_buy(
                cash, shares, avg_cost, next_open, signal, timestamp, trade_log
            )
        elif signal == "SELL":
            cash, shares, avg_cost = _execute_sell(
                cash, shares, avg_cost, next_open, timestamp, trade_log, closed_trade_pnls
            )

        equity = cash + (shares * float(row["close"]))
        equity_points.append({"timestamp": timestamp, "equity": float(equity)})

    final_ts = data.index[-1]
    final_equity = cash + (shares * float(data.iloc[-1]["close"]))
    equity_points.append({"timestamp": final_ts, "equity": float(final_equity)})

    equity_df = pd.DataFrame(equity_points)
    equity_df["timestamp"] = pd.to_datetime(equity_df["timestamp"], utc=True)

    metrics = calculate_metrics(
        equity_df["equity"],
        closed_trade_pnls,
        initial_capital,
        interval=interval,
    )
    metrics["ending_equity"] = float(final_equity)

    return equity_df, trade_log, metrics


def run_backtest(
    symbol: str = "SPY",
    period: str = "6mo",
    interval: str = "5m",
    force_interval: bool = False,
    initial_capital: float = 1000.0,
    plot: bool = False,
    output_csv: str | None = None,
) -> dict:
    data = fetch_ohlcv(
        symbol=symbol,
        period=period,
        interval=interval,
        force_interval=force_interval,
    )

    used_period = str(data.attrs.get("used_period", period))
    used_interval = str(data.attrs.get("used_interval", interval))

    equity_df, trade_log, metrics = simulate_backtest(
        data,
        initial_capital=initial_capital,
        interval=used_interval,
    )

    out_path = Path(output_csv) if output_csv else Path("logs") / f"equity_curve_{symbol}_{used_period}_{used_interval}.csv"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    equity_df.to_csv(out_path, index=False)

    result = {
        "symbol": symbol,
        "period": used_period,
        "interval": used_interval,
        "requested_period": period,
        "requested_interval": interval,
        "initial_capital": float(initial_capital),
        "equity_curve_csv": str(out_path),
        "trades": trade_log,
        "metrics": metrics,
    }

    if plot:
        import matplotlib.pyplot as plt

        plt.figure(figsize=(12, 5))
        plt.plot(equity_df["timestamp"], equity_df["equity"], label="Equity")
        plt.title(f"Equity Curve - {symbol} ({period}, {interval})")
        plt.xlabel("Time")
        plt.ylabel("Equity")
        plt.grid(alpha=0.25)
        plt.legend()
        plt.tight_layout()
        plt.show()

    return result


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="VWAP reversion strategy backtest")
    parser.add_argument("--symbol", default="SPY", help="Ticker symbol, e.g. SPY")
    parser.add_argument("--period", default="6mo", help="yfinance period, e.g. 6mo")
    parser.add_argument("--interval", default="5m", help="yfinance interval, e.g. 5m")
    parser.add_argument("--force-interval", action="store_true", help="Disable interval fallback to 60m/1d")
    parser.add_argument("--initial-capital", type=float, default=1000.0)
    parser.add_argument("--plot", action="store_true", help="Plot equity curve")
    parser.add_argument("--output-csv", default=None, help="Output path for equity curve CSV")
    return parser


def main() -> None:
    args = _build_arg_parser().parse_args()
    result = run_backtest(
        symbol=args.symbol,
        period=args.period,
        interval=args.interval,
        force_interval=args.force_interval,
        initial_capital=args.initial_capital,
        plot=args.plot,
        output_csv=args.output_csv,
    )
    metrics = result["metrics"]

    print(f"Backtest complete for {result['symbol']} ({result['period']}, {result['interval']})")
    print(f"Equity CSV: {result['equity_curve_csv']}")
    print(f"Total Return %: {metrics['total_return_pct']:.2f}")
    print(f"Sharpe Ratio: {metrics['sharpe_ratio']:.4f}")
    print(f"Max Drawdown %: {metrics['max_drawdown_pct']:.2f}")
    print(f"Win Rate %: {metrics['win_rate_pct']:.2f}")
    pf = metrics["profit_factor"]
    pf_str = "inf" if math.isinf(pf) else f"{pf:.4f}"
    print(f"Profit Factor: {pf_str}")
    print(f"Number of Trades: {metrics['number_of_trades']}")


if __name__ == "__main__":
    main()
