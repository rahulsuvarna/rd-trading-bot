import pandas as pd

from config.logger import get_logger
from strategies.vwap_reversion import generate_signal


def run_signals(pipeline_data: dict) -> dict:
    logger = get_logger(__name__)
    signals: dict = {}

    for ticker, df in pipeline_data.items():
        try:
            if not isinstance(df, pd.DataFrame):
                raise TypeError("pipeline_data values must be pandas DataFrame instances")
            signals[ticker] = generate_signal(ticker, df)
        except Exception as exc:
            logger.warning("Signal generation failed for %s: %s", ticker, exc)
            signals[ticker] = "HOLD"

    logger.info("SIGNAL SUMMARY | %s", signals)
    return signals
