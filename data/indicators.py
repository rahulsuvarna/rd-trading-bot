from pathlib import Path

import pandas as pd
import ta

from config.logger import get_logger

MODULE_DIR = Path(__file__).resolve().parent


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    logger = get_logger(__name__)

    enriched = df.copy()
    high = enriched["high"].astype(float)
    low = enriched["low"].astype(float)
    volume = enriched["volume"].astype(float)
    close_raw = enriched["close"].astype(float)
    typical_price = (high + low + close_raw) / 3

    # VWAP resets each trading day — compute while the datetime index is still present
    if isinstance(enriched.index, pd.DatetimeIndex):
        day_groups = enriched.index.normalize()
        enriched["vwap"] = (
            (typical_price * volume).groupby(day_groups).cumsum()
            / volume.groupby(day_groups).cumsum()
        )
    else:
        enriched["vwap"] = (typical_price * volume).cumsum() / volume.cumsum()

    # Reset to integer index so the ta library works reliably on all platforms
    enriched = enriched.reset_index(drop=True)
    close = enriched["close"].astype(float)
    enriched["ema_20"] = ta.trend.ema_indicator(close, window=20)
    enriched["rsi_14"] = ta.momentum.rsi(close, window=14)

    logger.debug(
        "Pre-dropna rows=%d  ema_20_nan=%d  rsi_14_nan=%d  vwap_nan=%d",
        len(enriched),
        int(enriched["ema_20"].isna().sum()),
        int(enriched["rsi_14"].isna().sum()),
        int(enriched["vwap"].isna().sum()),
    )
    enriched = enriched.dropna(subset=["ema_20", "rsi_14", "vwap"])
    logger.info("Indicators added for dataframe with %d rows", len(enriched))

    return enriched
