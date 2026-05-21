from pathlib import Path

import pandas as pd
import pandas_ta as ta

from config.logger import get_logger

MODULE_DIR = Path(__file__).resolve().parent


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    logger = get_logger(__name__)

    enriched = df.copy()
    enriched["ema_20"] = ta.ema(enriched["close"], length=20)
    enriched["rsi_14"] = ta.rsi(enriched["close"], length=14)
    enriched["vwap"] = ta.vwap(
        high=enriched["high"],
        low=enriched["low"],
        close=enriched["close"],
        volume=enriched["volume"],
    )

    enriched = enriched.dropna(subset=["ema_20", "rsi_14", "vwap"])
    logger.info("Indicators added for dataframe with %d rows", len(enriched))

    return enriched
