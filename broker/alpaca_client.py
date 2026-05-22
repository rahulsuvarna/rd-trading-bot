"""Alpaca paper trading broker client."""

import requests

from config.logger import get_logger
from config.settings import ALPACA_API_KEY, ALPACA_SECRET_KEY
from utils.ticker_utils import to_data_provider_symbol

ALPACA_PAPER_BASE_URL = "https://paper-api.alpaca.markets"

logger = get_logger(__name__)


class AlpacaClient:
    """Alpaca paper trading API client.

    Uses the Alpaca REST API v2 against the paper trading endpoint.
    Auth is via APCA-API-KEY-ID / APCA-API-SECRET-KEY headers.
    """

    def __init__(self) -> None:
        if not ALPACA_API_KEY or not ALPACA_SECRET_KEY:
            logger.warning("Alpaca API keys not configured — API calls will fail")

        self.base_url = ALPACA_PAPER_BASE_URL
        self.session = requests.Session()
        self.session.headers.update(
            {
                "APCA-API-KEY-ID": ALPACA_API_KEY or "",
                "APCA-API-SECRET-KEY": ALPACA_SECRET_KEY or "",
                "Content-Type": "application/json",
            }
        )

    def get_cash(self) -> float:
        """Return available cash from the Alpaca paper account."""
        try:
            response = self.session.get(
                f"{self.base_url}/v2/account", timeout=10
            )
            response.raise_for_status()
            data = response.json()
            return float(data.get("cash", 0))
        except Exception as exc:
            logger.exception("Failed to get Alpaca account cash: %s", exc)
            return 0.0

    def get_positions(self) -> dict:
        """Return current positions as {TICKER_US_EQ: float(shares)}."""
        try:
            response = self.session.get(
                f"{self.base_url}/v2/positions", timeout=10
            )
            response.raise_for_status()
            result: dict = {}
            for pos in response.json():
                symbol = str(pos.get("symbol", "")).upper()
                qty = float(pos.get("qty", 0))
                if symbol:
                    result[f"{symbol}_US_EQ"] = qty
            return result
        except Exception as exc:
            logger.exception("Failed to get Alpaca positions: %s", exc)
            return {}

    def execute_buy(self, ticker: str, amount: float) -> dict:
        """Place a notional market buy order on Alpaca paper.

        Args:
            ticker: Internal symbol, e.g. ``AAPL_US_EQ``.
            amount: Dollar amount to spend (notional order).

        Returns:
            Execution result dict with at minimum ``executed`` and ``mode``.
        """
        symbol = to_data_provider_symbol(ticker, "alpaca")
        try:
            payload = {
                "symbol": symbol,
                "notional": str(round(amount, 2)),
                "side": "buy",
                "type": "market",
                "time_in_force": "day",
            }
            response = self.session.post(
                f"{self.base_url}/v2/orders", json=payload, timeout=10
            )
            response.raise_for_status()
            data = response.json()
            logger.info(
                "ALPACA PAPER | BUY | %s | notional=£%.2f | order_id=%s",
                ticker,
                amount,
                data.get("id"),
            )
            return {
                "executed": True,
                "mode": "alpaca_paper",
                "ticker": ticker,
                "order_id": data.get("id"),
                "cost": amount,
            }
        except Exception as exc:
            logger.exception("Failed to execute Alpaca buy for %s: %s", ticker, exc)
            return {
                "executed": False,
                "mode": "alpaca_paper",
                "ticker": ticker,
                "reason": str(exc),
            }

    def execute_sell(self, ticker: str, shares: float) -> dict:
        """Place a qty-based market sell order on Alpaca paper.

        Args:
            ticker: Internal symbol, e.g. ``AAPL_US_EQ``.
            shares: Number of shares to sell.

        Returns:
            Execution result dict with at minimum ``executed`` and ``mode``.
        """
        symbol = to_data_provider_symbol(ticker, "alpaca")
        try:
            payload = {
                "symbol": symbol,
                "qty": str(round(shares, 6)),
                "side": "sell",
                "type": "market",
                "time_in_force": "day",
            }
            response = self.session.post(
                f"{self.base_url}/v2/orders", json=payload, timeout=10
            )
            response.raise_for_status()
            data = response.json()
            logger.info(
                "ALPACA PAPER | SELL | %s | qty=%.6f | order_id=%s",
                ticker,
                shares,
                data.get("id"),
            )
            return {
                "executed": True,
                "mode": "alpaca_paper",
                "ticker": ticker,
                "order_id": data.get("id"),
                "shares": shares,
            }
        except Exception as exc:
            logger.exception("Failed to execute Alpaca sell for %s: %s", ticker, exc)
            return {
                "executed": False,
                "mode": "alpaca_paper",
                "ticker": ticker,
                "reason": str(exc),
            }
