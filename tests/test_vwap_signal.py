import unittest

import pandas as pd

from strategies.vwap_reversion import generate_signal


def _build_base_df(rows: int = 25) -> pd.DataFrame:
    data = {
        "open": [100.0 + i for i in range(rows)],
        "high": [101.0 + i for i in range(rows)],
        "low": [99.0 + i for i in range(rows)],
        "close": [100.5 + i for i in range(rows)],
        "volume": [100000 + (i * 1000) for i in range(rows)],
        "ema_20": [100.2 + i for i in range(rows)],
        "rsi_14": [50.0 for _ in range(rows)],
        "vwap": [100.4 + i for i in range(rows)],
    }
    return pd.DataFrame(data)


class TestVWAPReversionSignal(unittest.TestCase):
    def test_buy_signal_when_close_below_vwap_and_rsi_below_40(self) -> None:
        df = _build_base_df()
        df.loc[df.index[-1], "close"] = 100.0
        df.loc[df.index[-1], "vwap"] = 101.0
        df.loc[df.index[-1], "rsi_14"] = 35.0

        signal = generate_signal("SPY", df)
        self.assertEqual(signal, "BUY")

    def test_sell_signal_when_close_above_vwap_and_rsi_above_60(self) -> None:
        df = _build_base_df()
        df.loc[df.index[-1], "close"] = 102.0
        df.loc[df.index[-1], "vwap"] = 101.0
        df.loc[df.index[-1], "rsi_14"] = 65.0

        signal = generate_signal("QQQ", df)
        self.assertEqual(signal, "SELL")

    def test_hold_signal_for_neutral_row(self) -> None:
        df = _build_base_df()
        df.loc[df.index[-1], "close"] = 101.0
        df.loc[df.index[-1], "vwap"] = 101.0
        df.loc[df.index[-1], "rsi_14"] = 50.0

        signal = generate_signal("AAPL", df)
        self.assertEqual(signal, "HOLD")

    def test_empty_dataframe_returns_hold_safely(self) -> None:
        df = pd.DataFrame()

        signal = generate_signal("MSFT", df)
        self.assertEqual(signal, "HOLD")


if __name__ == "__main__":
    unittest.main()
