"""CLI dashboard for trading bot state reconstructed from journal.db."""

import json
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path

import yfinance as yf

# Allow running via: python scripts/dashboard.py
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import PAPER_STARTING_CASH, PROJECT_ROOT, TRADING_MODE


class TradingDashboard:
    """Reconstructs account state from journal cycles and renders CLI output."""

    def __init__(self, db_path: Path | None = None, refresh_interval: int = 5):
        self.db_path = db_path or (PROJECT_ROOT / "logs" / "journal.db")
        self.refresh_interval = refresh_interval
        self.mode = TRADING_MODE
        self.starting_cash = float(PAPER_STARTING_CASH)
        self.cash = float(PAPER_STARTING_CASH)
        self.positions: dict[str, dict[str, float]] = {}
        self.trade_history: list[dict] = []

    def reset_state(self) -> None:
        """Reset reconstructed state back to configured defaults."""
        self.cash = self.starting_cash
        self.positions = {}
        self.trade_history = []

    def load_journal(self) -> bool:
        """Load and process all cycles in ascending order from the journal DB."""
        if not Path(self.db_path).exists():
            return False

        self.reset_state()

        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        cursor = connection.cursor()
        cursor.execute("SELECT timestamp, signals, orders_executed FROM cycles ORDER BY id ASC")
        rows = cursor.fetchall()
        connection.close()

        for row in rows:
            timestamp = row["timestamp"]
            signals_raw = row["signals"]
            orders_executed = int(row["orders_executed"] or 0)

            try:
                signals = json.loads(signals_raw) if signals_raw else {}
            except json.JSONDecodeError:
                signals = {}

            self._process_cycle(timestamp, signals, orders_executed)

        return True

    def _process_cycle(self, timestamp: str, signals: dict, orders_executed: int) -> None:
        """Process one cycle payload into positions, cash, and trade history."""
        if not isinstance(signals, dict):
            return

        remaining_executions = orders_executed

        for ticker, signal_payload in signals.items():
            action = None
            price = None
            shares = None
            amount = None
            executed = False

            if isinstance(signal_payload, dict):
                action = str(signal_payload.get("signal", "")).upper()
                price_value = signal_payload.get("price")
                if price_value is not None:
                    price = float(price_value)

                shares_value = signal_payload.get("shares")
                if shares_value is not None:
                    shares = float(shares_value)

                amount_value = signal_payload.get("amount")
                if amount_value is not None:
                    amount = float(amount_value)

                executed = bool(signal_payload.get("executed", False))
            elif isinstance(signal_payload, str):
                action = signal_payload.upper()

            if action not in {"BUY", "SELL"}:
                continue

            if not executed and remaining_executions > 0:
                executed = True
                remaining_executions -= 1

            if not executed:
                continue

            if price is None or price <= 0:
                continue

            if action == "BUY":
                if shares is None and amount is not None:
                    shares = round(amount / price, 6)
                if shares is None or shares <= 0:
                    continue
                self._apply_buy(timestamp, ticker, shares, price)
            else:
                if shares is None or shares <= 0:
                    continue
                self._apply_sell(timestamp, ticker, shares, price)

    def _apply_buy(self, timestamp: str, ticker: str, shares: float, price: float) -> None:
        cost = round(shares * price, 6)
        current = self.positions.get(ticker, {"shares": 0.0, "avg_cost": 0.0})
        existing_shares = float(current["shares"])
        existing_avg = float(current["avg_cost"])

        total_shares = round(existing_shares + shares, 6)
        total_cost = (existing_shares * existing_avg) + cost
        avg_cost = round(total_cost / total_shares, 6) if total_shares > 0 else 0.0

        self.positions[ticker] = {"shares": total_shares, "avg_cost": avg_cost}
        self.cash = round(self.cash - cost, 6)
        self.trade_history.append(
            {
                "timestamp": timestamp,
                "ticker": ticker,
                "action": "BUY",
                "shares": shares,
                "price": price,
            }
        )

    def _apply_sell(self, timestamp: str, ticker: str, shares: float, price: float) -> None:
        current = self.positions.get(ticker)
        if not current:
            return

        existing_shares = float(current["shares"])
        if existing_shares <= 0:
            return

        sell_shares = min(shares, existing_shares)
        proceeds = round(sell_shares * price, 6)
        remaining = round(existing_shares - sell_shares, 6)

        if remaining <= 0:
            self.positions.pop(ticker, None)
        else:
            self.positions[ticker]["shares"] = remaining

        self.cash = round(self.cash + proceeds, 6)
        self.trade_history.append(
            {
                "timestamp": timestamp,
                "ticker": ticker,
                "action": "SELL",
                "shares": sell_shares,
                "price": price,
            }
        )

    def fetch_current_prices(self) -> dict[str, float]:
        """Fetch current prices for all open positions via yfinance."""
        prices: dict[str, float] = {}
        for ticker in self.positions:
            symbol = ticker.replace("_US_EQ", "")
            try:
                data = yf.Ticker(symbol).history(period="1d", interval="1m")
                if not data.empty:
                    prices[ticker] = float(data["Close"].iloc[-1])
            except Exception:
                continue
        return prices

    def _portfolio_metrics(self, prices: dict[str, float]) -> tuple[float, float, float]:
        total_market_value = 0.0
        total_unrealized = 0.0

        for ticker, pos in self.positions.items():
            shares = float(pos["shares"])
            avg_cost = float(pos["avg_cost"])
            current_price = prices.get(ticker, avg_cost)
            market_value = shares * current_price
            unrealized = (current_price - avg_cost) * shares
            total_market_value += market_value
            total_unrealized += unrealized

        portfolio_value = self.cash + total_market_value
        return portfolio_value, total_market_value, total_unrealized

    def render(self) -> None:
        """Render dashboard output to console."""
        prices = self.fetch_current_prices()
        portfolio_value, total_market_value, total_unrealized = self._portfolio_metrics(prices)

        print("\x1b[2J\x1b[H", end="")
        print("=" * 80)
        print(f"Trading Bot Dashboard | {datetime.utcnow().isoformat()} UTC")
        print("=" * 80)
        print(f"Mode: {self.mode.upper()}")
        print(f"Cash: £{self.cash:.2f}")
        print(f"Positions: {len(self.positions)}")
        print(f"Market Value: £{total_market_value:.2f}")
        print(f"Portfolio Value: £{portfolio_value:.2f}")
        print(f"Unrealized P&L: £{total_unrealized:.2f}")
        print("-" * 80)
        print("Positions")
        print("Ticker        Shares        Avg Cost     Current      P&L")
        print("-" * 80)

        for ticker, pos in self.positions.items():
            shares = float(pos["shares"])
            avg_cost = float(pos["avg_cost"])
            current_price = prices.get(ticker, avg_cost)
            pnl = (current_price - avg_cost) * shares
            print(
                f"{ticker:<12} {shares:>10.6f}   £{avg_cost:>8.2f}   £{current_price:>8.2f}   £{pnl:>8.2f}"
            )

        print("-" * 80)
        print("Last 5 Trades")
        print("Timestamp                  Ticker        Action   Shares      Price")
        print("-" * 80)

        for trade in self.trade_history[-5:][::-1]:
            print(
                f"{trade['timestamp']:<25} {trade['ticker']:<12} {trade['action']:<7} "
                f"{trade['shares']:>10.6f}   £{trade['price']:>8.2f}"
            )

        print("=" * 80)

    def run(self) -> None:
        """Start auto-refresh dashboard loop."""
        try:
            while True:
                loaded = self.load_journal()
                if not loaded:
                    print(f"Journal not found at: {self.db_path}")
                else:
                    self.render()
                time.sleep(self.refresh_interval)
        except KeyboardInterrupt:
            print("\nDashboard stopped by user.")


if __name__ == "__main__":
    TradingDashboard().run()
