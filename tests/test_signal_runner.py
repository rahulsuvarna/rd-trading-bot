import unittest

import pandas as pd

from strategies.signal_runner import run_signals


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


class TestSignalRunner(unittest.TestCase):
    def test_run_signals_returns_all_tickers(self) -> None:
        buy_df = _build_base_df()
        buy_df.loc[buy_df.index[-1], "close"] = 100.0
        buy_df.loc[buy_df.index[-1], "vwap"] = 101.0
        buy_df.loc[buy_df.index[-1], "rsi_14"] = 35.0

        sell_df = _build_base_df()
        sell_df.loc[sell_df.index[-1], "close"] = 102.0
        sell_df.loc[sell_df.index[-1], "vwap"] = 101.0
        sell_df.loc[sell_df.index[-1], "rsi_14"] = 65.0

        hold_df = _build_base_df()
        hold_df.loc[hold_df.index[-1], "close"] = 101.0
        hold_df.loc[hold_df.index[-1], "vwap"] = 101.0
        hold_df.loc[hold_df.index[-1], "rsi_14"] = 50.0

        pipeline_data = {"SPY": buy_df, "QQQ": sell_df, "AAPL": hold_df}
        signals = run_signals(pipeline_data)

        self.assertEqual(set(signals.keys()), {"SPY", "QQQ", "AAPL"})

    def test_run_signals_returns_expected_values(self) -> None:
        buy_df = _build_base_df()
        buy_df.loc[buy_df.index[-1], "close"] = 100.0
        buy_df.loc[buy_df.index[-1], "vwap"] = 101.0
        buy_df.loc[buy_df.index[-1], "rsi_14"] = 35.0

        sell_df = _build_base_df()
        sell_df.loc[sell_df.index[-1], "close"] = 102.0
        sell_df.loc[sell_df.index[-1], "vwap"] = 101.0
        sell_df.loc[sell_df.index[-1], "rsi_14"] = 65.0

        hold_df = _build_base_df()
        hold_df.loc[hold_df.index[-1], "close"] = 101.0
        hold_df.loc[hold_df.index[-1], "vwap"] = 101.0
        hold_df.loc[hold_df.index[-1], "rsi_14"] = 50.0

        pipeline_data = {"SPY": buy_df, "QQQ": sell_df, "AAPL": hold_df}
        signals = run_signals(pipeline_data)

        self.assertEqual(signals["SPY"], "BUY")
        self.assertEqual(signals["QQQ"], "SELL")
        self.assertEqual(signals["AAPL"], "HOLD")

    def test_run_signals_with_empty_dict_returns_empty_dict(self) -> None:
        signals = run_signals({})
        self.assertEqual(signals, {})


if __name__ == "__main__":
    unittest.main()
