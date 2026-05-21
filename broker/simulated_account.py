"""Simulated account for paper trading - no live broker calls."""


class SimulatedAccount:
    """In-memory account state for paper mode testing."""

    def __init__(self, starting_cash: float = 1000.0):
        """
        Initialize simulated account.

        Args:
            starting_cash: Initial cash balance (default GBP1000)
        """
        self.cash = starting_cash
        self.positions = {}  # ticker -> shares held
        self.trade_history = []  # list of trade dicts

    def get_cash(self) -> float:
        """Return current cash balance."""
        return self.cash

    def get_positions(self) -> dict:
        """Return copy of current positions (ticker -> shares)."""
        return dict(self.positions)

    def execute_buy(self, ticker: str, amount: float, price: float) -> dict:
        """
        Simulate a buy order.

        Args:
            ticker: Stock symbol (e.g., "AAPL_US_EQ")
            amount: Pound amount to spend
            price: Current price per share

        Returns:
            Dict with keys: executed, ticker, shares, cost, price, remaining_cash
            If insufficient cash: executed=False, reason key
        """
        if amount <= 0 or price <= 0:
            return {
                "executed": False,
                "ticker": ticker,
                "reason": "invalid_order",
            }

        if amount > self.cash:
            return {
                "executed": False,
                "ticker": ticker,
                "reason": "insufficient_cash",
            }

        shares = round(amount / price, 6)
        cost = round(shares * price, 6)
        self.cash = round(self.cash - cost, 6)

        current = self.positions.get(ticker, 0.0)
        self.positions[ticker] = round(current + shares, 6)

        trade = {
            "side": "BUY",
            "ticker": ticker,
            "shares": shares,
            "price": price,
            "value": cost,
        }
        self.trade_history.append(trade)

        return {
            "executed": True,
            "ticker": ticker,
            "shares": shares,
            "cost": cost,
            "price": price,
            "remaining_cash": self.cash,
        }

    def execute_sell(self, ticker: str, shares: float, price: float) -> dict:
        """
        Simulate a sell order.

        Args:
            ticker: Stock symbol
            shares: Number of shares to sell
            price: Current price per share

        Returns:
            Dict with keys: executed, ticker, shares, proceeds, price, remaining_cash
            If insufficient shares: executed=False, reason key
        """
        if shares <= 0 or price <= 0:
            return {
                "executed": False,
                "ticker": ticker,
                "reason": "invalid_order",
            }

        held = self.positions.get(ticker, 0.0)
        if held < shares:
            return {
                "executed": False,
                "ticker": ticker,
                "reason": "insufficient_shares",
            }

        proceeds = round(shares * price, 6)
        self.cash = round(self.cash + proceeds, 6)

        remaining = round(held - shares, 6)
        if remaining <= 0:
            self.positions.pop(ticker, None)
        else:
            self.positions[ticker] = remaining

        trade = {
            "side": "SELL",
            "ticker": ticker,
            "shares": shares,
            "price": price,
            "value": proceeds,
        }
        self.trade_history.append(trade)

        return {
            "executed": True,
            "ticker": ticker,
            "shares": shares,
            "proceeds": proceeds,
            "price": price,
            "remaining_cash": self.cash,
        }

    def reset(self, starting_cash: float = 1000.0) -> None:
        """Reset account to fresh state."""
        self.cash = starting_cash
        self.positions = {}
        self.trade_history = []
