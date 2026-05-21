import unittest

from risk.daily_loss_tracker import (
    get_summary,
    initialise,
    is_trading_allowed,
    record_trade_result,
)


class TestDailyLossTracker(unittest.TestCase):
    def test_initialise_sets_capital_and_trading_allowed_true(self) -> None:
        initialise(1000.0)
        summary = get_summary()

        self.assertEqual(summary["starting_capital"], 1000.0)
        self.assertEqual(summary["current_capital"], 1000.0)
        self.assertTrue(is_trading_allowed())

    def test_small_loss_does_not_trigger_kill_switch(self) -> None:
        initialise(1000.0)
        record_trade_result(-10.0)

        self.assertTrue(is_trading_allowed())

    def test_exact_five_percent_loss_triggers_kill_switch(self) -> None:
        initialise(1000.0)
        record_trade_result(-50.0)

        self.assertFalse(is_trading_allowed())

    def test_loss_beyond_five_percent_triggers_kill_switch(self) -> None:
        initialise(1000.0)
        record_trade_result(-60.0)

        self.assertFalse(is_trading_allowed())

    def test_profit_never_triggers_kill_switch(self) -> None:
        initialise(1000.0)
        record_trade_result(100.0)

        self.assertTrue(is_trading_allowed())

    def test_once_killed_trading_allowed_returns_false(self) -> None:
        initialise(1000.0)
        record_trade_result(-60.0)
        record_trade_result(20.0)

        self.assertFalse(is_trading_allowed())

    def test_get_summary_returns_expected_keys(self) -> None:
        initialise(1000.0)
        summary = get_summary()

        expected = {
            "starting_capital",
            "current_capital",
            "pnl",
            "loss_pct",
            "is_killed",
        }
        self.assertEqual(set(summary.keys()), expected)


if __name__ == "__main__":
    unittest.main()
