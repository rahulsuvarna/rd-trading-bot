import unittest

from risk.position_sizer import calculate_trade_amount


class TestPositionSizer(unittest.TestCase):
    def test_hold_signal_returns_zero(self) -> None:
        result = calculate_trade_amount("HOLD", 1000.0)
        self.assertEqual(result, 0.0)

    def test_capital_1000_returns_ten(self) -> None:
        result = calculate_trade_amount("BUY", 1000.0)
        self.assertEqual(result, 10.0)

    def test_capital_500_returns_five(self) -> None:
        result = calculate_trade_amount("BUY", 500.0)
        self.assertEqual(result, 5.0)

    def test_capital_50_returns_zero_due_to_minimum(self) -> None:
        result = calculate_trade_amount("BUY", 50.0)
        self.assertEqual(result, 0.0)

    def test_zero_capital_returns_zero(self) -> None:
        result = calculate_trade_amount("BUY", 0.0)
        self.assertEqual(result, 0.0)

    def test_negative_capital_returns_zero(self) -> None:
        result = calculate_trade_amount("BUY", -100.0)
        self.assertEqual(result, 0.0)


if __name__ == "__main__":
    unittest.main()
