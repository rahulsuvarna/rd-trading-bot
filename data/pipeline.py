from pathlib import Path

from config.logger import get_logger
from config.settings import DATA_PROVIDER
from config.watchlist import WATCHLIST
from data.indicators import add_indicators
from data.price_fetcher import fetch_prices
from utils.ticker_utils import to_data_provider_symbol

MODULE_DIR = Path(__file__).resolve().parent


def run_pipeline() -> dict:
    logger = get_logger(__name__)
    output: dict = {}

    for ticker in WATCHLIST:
        provider_ticker = to_data_provider_symbol(ticker, DATA_PROVIDER)
        prices = fetch_prices(provider_ticker)
        if prices is None:
            logger.warning("Skipping %s due to fetch failure", ticker)
            continue

        enriched = add_indicators(prices)
        if enriched.empty:
            logger.warning("Skipping %s because indicator dataframe is empty", ticker)
            continue

        latest = enriched.iloc[-1]
        logger.info(
            "%s | close=%.2f | rsi=%.2f | ema20=%.2f | vwap=%.2f",
            ticker,
            float(latest["close"]),
            float(latest["rsi_14"]),
            float(latest["ema_20"]),
            float(latest["vwap"]),
        )

        output[ticker] = enriched

    return output
