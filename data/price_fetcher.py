from __future__ import annotations

from pathlib import Path

import pandas as pd
import yfinance as yf

from config.logger import get_logger
from config.settings import DATA_PROVIDER
from config.watchlist import INTERVAL, PERIOD
from utils.ticker_utils import to_data_provider_symbol

MODULE_DIR = Path(__file__).resolve().parent


def to_yahoo_symbol(ticker: str) -> str:
    """Convert Trading 212 format (AAPL_US_EQ) to Yahoo format (AAPL)."""
    return to_data_provider_symbol(ticker, "yahoo")


def fetch_prices(ticker: str) -> pd.DataFrame | None:
    logger = get_logger(__name__)
    provider_ticker = to_data_provider_symbol(ticker, DATA_PROVIDER)

    try:
        raw_df = yf.download(
            tickers=provider_ticker,
            interval=INTERVAL,
            period=PERIOD,
            progress=False,
            auto_adjust=False,
            threads=False,
        )

        if raw_df is None or raw_df.empty:
            logger.warning("Price fetch returned no data for %s", ticker)
            return None

        if isinstance(raw_df.columns, pd.MultiIndex):
            raw_df.columns = [str(col[0]).lower() for col in raw_df.columns]
        else:
            raw_df.columns = [str(col).lower() for col in raw_df.columns]

        required_columns = ["open", "high", "low", "close", "volume"]
        missing_columns = [col for col in required_columns if col not in raw_df.columns]
        if missing_columns:
            logger.warning(
                "Price fetch missing required columns for %s: %s",
                ticker,
                ", ".join(missing_columns),
            )
            return None

        df = raw_df[required_columns].copy()
        df = df.dropna(subset=["close"])

        if df.empty:
            logger.warning("Price data is empty after cleanup for %s", ticker)
            return None

        return df
    except Exception as exc:
        logger.warning("Failed to fetch prices for %s: %s", ticker, exc)
        return None
