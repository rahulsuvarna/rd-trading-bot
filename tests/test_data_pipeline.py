import unittest

from data.indicators import add_indicators
from data.price_fetcher import fetch_prices


class TestDataPipeline(unittest.TestCase):
    def test_fetch_prices_returns_dataframe(self) -> None:
        df = fetch_prices("SPY")
        self.assertIsNotNone(df)
        self.assertFalse(df.empty)

    def test_fetch_prices_has_required_columns(self) -> None:
        df = fetch_prices("SPY")
        self.assertIsNotNone(df)

        required = {"open", "high", "low", "close", "volume"}
        self.assertTrue(required.issubset(set(df.columns)))

    def test_add_indicators_adds_expected_columns(self) -> None:
        df = fetch_prices("SPY")
        self.assertIsNotNone(df)

        enriched = add_indicators(df)
        expected = {"ema_20", "rsi_14", "vwap"}
        self.assertTrue(expected.issubset(set(enriched.columns)))

    def test_final_dataframe_has_no_nans(self) -> None:
        df = fetch_prices("SPY")
        self.assertIsNotNone(df)

        enriched = add_indicators(df)
        self.assertFalse(enriched.isna().any().any())


if __name__ == "__main__":
    unittest.main()
