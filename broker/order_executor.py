"""Order execution abstraction with paper and live modes."""

from typing import TYPE_CHECKING, Any, Dict, Optional

from broker.simulated_account import SimulatedAccount
from config.logger import get_logger
from config.settings import IS_PAPER_MODE

if TYPE_CHECKING:
    from broker.t212_client import T212Client


class OrderExecutor:
    """Executes orders in either paper or live mode."""

    def __init__(
        self,
        mode: str = "paper",
        starting_paper_cash: float = 1000.0,
        live_client: Optional[Any] = None,
    ):
        """
        Initialize order executor.

        Args:
            mode: "paper" or "live"
            starting_paper_cash: Initial cash for paper mode simulation
            live_client: Trading 212 client instance (only used in live mode)
        """
        self.mode = mode.lower()
        self.paper_account = (
            SimulatedAccount(starting_cash=starting_paper_cash)
            if self.mode == "paper"
            else None
        )
        self.live_client = live_client

    def get_available_cash(self) -> float:
        """Get available cash based on current mode."""
        if self.mode == "paper":
            return self.paper_account.get_cash()

        if self.live_client is None:
            raise RuntimeError(f"{self.mode.title()} client not provided")
        return self.live_client.get_cash()

    def get_positions(self) -> Dict[str, float]:
        """Get current positions based on mode."""
        if self.mode == "paper":
            return self.paper_account.get_positions()

        if self.live_client is None:
            raise RuntimeError(f"{self.mode.title()} client not provided")
        return self.live_client.get_positions()

    def execute_order(
        self, ticker: str, signal: str, amount: float, price: float
    ) -> Dict[str, Any]:
        """
        Execute an order based on mode.

        Args:
            ticker: Stock symbol
            signal: "BUY" or "SELL"
            amount: Pound amount for buy, or shares for sell
            price: Current price per share

        Returns:
            Dict with execution result
        """
        if self.mode == "paper":
            if signal.upper() == "BUY":
                return self.paper_account.execute_buy(ticker, amount, price)
            if signal.upper() == "SELL":
                # For sells, amount is number of shares to sell
                return self.paper_account.execute_sell(ticker, amount, price)
            return {"executed": False, "reason": f"Unknown signal: {signal}"}

        if self.mode == "alpaca":
            if self.live_client is None:
                raise RuntimeError("Alpaca client not provided")
            if signal.upper() == "BUY":
                return self.live_client.execute_buy(ticker, amount)
            if signal.upper() == "SELL":
                # amount is shares for sell orders
                return self.live_client.execute_sell(ticker, amount)
            return {"executed": False, "reason": f"Unknown signal: {signal}"}

        # T212 live mode - not yet implemented
        return {
            "executed": False,
            "mode": "live",
            "reason": "Live execution not implemented",
            "note": f"Would have {signal} {amount} of {ticker} at ~{price}",
        }

    def reset_paper_account(self, starting_cash: float = 1000.0) -> None:
        """Reset paper account to fresh state (paper mode only)."""
        if self.mode == "paper" and self.paper_account:
            self.paper_account.reset(starting_cash)


def execute_order(decision: dict, client: "T212Client") -> dict:
    """Backward-compatible adapter for the existing trading loop path."""
    logger = get_logger(__name__)
    _ = client
    signal = decision["signal"]
    trade_amount = decision["trade_amount"]

    if not decision["approved"]:
        return {
            "executed": False,
            "mode": "unknown",
            "signal": signal,
            "trade_amount": trade_amount,
            "note": decision["reason"],
        }

    if IS_PAPER_MODE:
        logger.info(
            "PAPER ORDER | signal=%s | amount=£%.2f | simulated only",
            signal,
            trade_amount,
        )
        return {
            "executed": True,
            "mode": "paper",
            "signal": signal,
            "trade_amount": trade_amount,
            "note": "simulated",
        }

    logger.warning("LIVE ORDER | not yet implemented — refusing to execute")
    return {
        "executed": False,
        "mode": "live",
        "signal": signal,
        "trade_amount": trade_amount,
        "note": "not_implemented",
    }
