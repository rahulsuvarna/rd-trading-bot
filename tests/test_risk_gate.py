import unittest

from risk.daily_loss_tracker import initialise, record_trade_result
from risk.risk_gate import evaluate


class TestRiskGate(unittest.TestCase):
    def setUp(self) -> None:
        initialise(1000.0)

    def test_hold_signal_is_not_approved(self) -> None:
        decision = evaluate("HOLD", 1000.0)

        self.assertFalse(decision["approved"])
        self.assertEqual(decision["reason"], "signal_is_hold")

    def test_buy_signal_with_valid_capital_is_approved(self) -> None:
        decision = evaluate("BUY", 1000.0)

        self.assertTrue(decision["approved"])
        self.assertEqual(decision["trade_amount"], 10.0)

    def test_sell_signal_with_valid_capital_is_approved(self) -> None:
        decision = evaluate("SELL", 1000.0)

        self.assertTrue(decision["approved"])
        self.assertEqual(decision["trade_amount"], 10.0)

    def test_kill_switch_blocks_any_signal(self) -> None:
        record_trade_result(-60.0)

        decision = evaluate("BUY", 1000.0)
        self.assertFalse(decision["approved"])
        self.assertEqual(decision["reason"], "kill_switch_active")

    def test_small_capital_returns_trade_amount_too_small(self) -> None:
        decision = evaluate("BUY", 50.0)

        self.assertFalse(decision["approved"])
        self.assertEqual(decision["reason"], "trade_amount_too_small")


if __name__ == "__main__":
    unittest.main()
