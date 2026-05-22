import unittest
from unittest.mock import MagicMock, patch

import requests

from monitoring.telegram_alert import alert_cycle_detail, alert_signal_fired, send_alert


class TestTelegramAlert(unittest.TestCase):
    @patch("monitoring.telegram_alert.TELEGRAM_CHAT_ID", "chat-id")
    @patch("monitoring.telegram_alert.TELEGRAM_BOT_TOKEN", "token")
    @patch("monitoring.telegram_alert.requests.post")
    def test_send_alert_returns_true_on_200(self, mock_post: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        result = send_alert("hello")

        self.assertTrue(result)

    @patch("monitoring.telegram_alert.TELEGRAM_CHAT_ID", "chat-id")
    @patch("monitoring.telegram_alert.TELEGRAM_BOT_TOKEN", "token")
    @patch("monitoring.telegram_alert.requests.post")
    def test_send_alert_returns_false_on_400(self, mock_post: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_post.return_value = mock_response

        result = send_alert("hello")

        self.assertFalse(result)

    @patch("monitoring.telegram_alert.TELEGRAM_CHAT_ID", "chat-id")
    @patch("monitoring.telegram_alert.TELEGRAM_BOT_TOKEN", "token")
    @patch("monitoring.telegram_alert.requests.post")
    def test_send_alert_returns_false_on_timeout(self, mock_post: MagicMock) -> None:
        mock_post.side_effect = requests.exceptions.Timeout("timed out")

        result = send_alert("hello")

        self.assertFalse(result)

    @patch("monitoring.telegram_alert.TELEGRAM_CHAT_ID", "chat-id")
    @patch("monitoring.telegram_alert.TELEGRAM_BOT_TOKEN", "")
    @patch("monitoring.telegram_alert.logger")
    def test_send_alert_returns_false_when_token_empty(
        self, mock_logger: MagicMock
    ) -> None:
        result = send_alert("hello")

        self.assertTrue(result)
        mock_logger.debug.assert_called_once()

    @patch("monitoring.telegram_alert.send_alert")
    def test_alert_signal_fired_calls_send_alert_with_expected_message(
        self, mock_send_alert: MagicMock
    ) -> None:
        mock_send_alert.return_value = True

        alert_signal_fired("SPY", "BUY", 10.0)

        self.assertTrue(mock_send_alert.called)
        sent_message = mock_send_alert.call_args[0][0]
        self.assertIn("SPY", sent_message)
        self.assertIn("BUY", sent_message)
        self.assertIn("10.00", sent_message)

    @patch("monitoring.telegram_alert.send_alert")
    def test_alert_cycle_detail_sends_executed_line_for_buy(self, mock_send_alert: MagicMock) -> None:
        mock_send_alert.return_value = True
        cycle_result = {
            "signals": {
                "AAPL_US_EQ": {
                    "signal": "BUY",
                    "executed": True,
                    "cost": 10.0,
                },
                "SPY_US_EQ": "HOLD",
            },
            "free_cash": 990.0,
        }

        result = alert_cycle_detail(cycle_result)

        self.assertTrue(result)
        mock_send_alert.assert_called_once()
        sent_message = mock_send_alert.call_args[0][0]
        self.assertIn("AAPL_US_EQ", sent_message)
        self.assertIn("✅", sent_message)


if __name__ == "__main__":
    unittest.main()
