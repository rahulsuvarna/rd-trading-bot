import requests

from config.logger import get_logger
from config.settings import (
    ENV,
    TRADING212_ACCOUNT_TYPE,
    TRADING212_API_KEY,
    TRADING212_API_SECRET,
)

logger = get_logger(__name__)

# Base URLs for Trading 212 API
BASE_URL_LIVE = "https://api.trading212.com/v1"
BASE_URL_DEMO = "https://demo.trading212.com/api/v1"


class T212Client:
    """Trading 212 API client."""

    def __init__(self):
        """Initialize client with API keys from settings."""
        self.api_key = TRADING212_API_KEY
        self.api_secret = TRADING212_API_SECRET
        self.account_type = TRADING212_ACCOUNT_TYPE

        # Determine base URL based on ENV
        self.base_url = BASE_URL_DEMO if ENV == "sandbox" else BASE_URL_LIVE

        if not self.api_key:
            logger.warning("TRADING212_API_KEY not set - API calls will fail")

        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
        )

    def get_cash(self) -> float:
        """Get available cash balance."""
        try:
            response = self.session.get(f"{self.base_url}/account/cash")
            response.raise_for_status()
            data = response.json()
            return float(data.get("cash", 0))
        except Exception as exc:
            logger.exception("Failed to get cash: %s", exc)
            return 0.0

    def get_account_cash(self) -> dict | None:
        """Backward-compatible cash payload for older call sites."""
        cash = self.get_cash()
        return {"free": cash, "total": cash}

    def get_positions(self) -> dict:
        """Get current positions as {ticker: shares}."""
        try:
            response = self.session.get(f"{self.base_url}/portfolio")
            response.raise_for_status()
            positions = response.json()
            result = {}
            for pos in positions:
                ticker = pos.get("ticker")
                shares = pos.get("quantity", 0)
                if ticker:
                    result[ticker] = float(shares)
            return result
        except Exception as exc:
            logger.exception("Failed to get positions: %s", exc)
            return {}
