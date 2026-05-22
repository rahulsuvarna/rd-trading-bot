from pathlib import Path

import pandas as pd
import ta

from config.logger import get_logger

MODULE_DIR = Path(__file__).resolve().parent


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    logger = get_logger(__name__)

    enriched = df.copy()
    enriched["ema_20"] = ta.trend.ema_indicator(enriched["close"], window=20)
    enriched["rsi_14"] = ta.momentum.rsi(enriched["close"], window=14)
    typical_price = (enriched["high"] + enriched["low"] + enriched["close"]) / 3
    enriched["vwap"] = (typical_price * enriched["volume"]).cumsum() / enriched[
        "volume"
    ].cumsum()

    enriched = enriched.dropna(subset=["ema_20", "rsi_14", "vwap"])
    logger.info("Indicators added for dataframe with %d rows", len(enriched))

    return enriched
