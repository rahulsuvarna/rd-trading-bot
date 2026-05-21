import pandas as pd

from config.logger import get_logger


def generate_signal(ticker: str, df: pd.DataFrame) -> str:
    logger = get_logger(__name__)
    required_columns = {"close", "rsi_14", "vwap"}

    if df.empty or not required_columns.issubset(set(df.columns)):
        logger.warning("SIGNAL | %s | HOLD | close=0.00 | rsi=0.00 | vwap=0.00", ticker)
        return "HOLD"

    latest = df.iloc[-1]
    close = float(latest["close"])
    rsi = float(latest["rsi_14"])
    vwap = float(latest["vwap"])

    if close < vwap and rsi < 40:
        signal = "BUY"
    elif close > vwap and rsi > 60:
        signal = "SELL"
    else:
        signal = "HOLD"

    logger.info(
        "SIGNAL | %s | %s | close=%.2f | rsi=%.2f | vwap=%.2f",
        ticker,
        signal,
        close,
        rsi,
        vwap,
    )
    return signal
