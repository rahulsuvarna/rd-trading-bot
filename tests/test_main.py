import unittest
from unittest.mock import MagicMock, patch

import main
from main import trading_job


class TestMainTradingJob(unittest.TestCase):
    def setUp(self) -> None:
        self.mock_client = MagicMock()
        main.client = self.mock_client

    @patch("main.send_alert")
    @patch("main.T212Client")
    @patch("main.get_summary")
    @patch("main.record_cycle")
    @patch("main.run_trading_cycle")
    def test_trading_job_calls_cycle_and_record_once(
        self,
        mock_run_trading_cycle: MagicMock,
        mock_record_cycle: MagicMock,
        mock_get_summary: MagicMock,
        mock_t212_client: MagicMock,
        mock_send_alert: MagicMock,
    ) -> None:
        result = {"status": "aborted", "reason": "no_free_cash"}
        mock_run_trading_cycle.return_value = result
        mock_get_summary.return_value = {"is_killed": False, "loss_pct": 0.0}

        trading_job()

        mock_run_trading_cycle.assert_called_once_with(self.mock_client)
        mock_record_cycle.assert_called_once_with(result)

    @patch("main.send_alert")
    @patch("main.T212Client")
    @patch("main.alert_cycle_summary")
    @patch("main.get_summary")
    @patch("main.record_cycle")
    @patch("main.run_trading_cycle")
    def test_trading_job_calls_alert_cycle_summary_when_completed(
        self,
        mock_run_trading_cycle: MagicMock,
        mock_record_cycle: MagicMock,
        mock_get_summary: MagicMock,
        mock_alert_cycle_summary: MagicMock,
        mock_t212_client: MagicMock,
        mock_send_alert: MagicMock,
    ) -> None:
        result = {
            "status": "completed",
            "orders": [
                {
                    "executed": True,
                    "mode": "paper",
                    "signal": "BUY",
                    "trade_amount": 10.0,
                    "note": "simulated",
                }
            ],
        }
        mock_run_trading_cycle.return_value = result
        mock_get_summary.return_value = {"is_killed": False, "loss_pct": 0.0}

        trading_job()

        mock_alert_cycle_summary.assert_called_once_with("completed", 1)

    @patch("main.send_alert")
    @patch("main.T212Client")
    @patch("main.alert_cycle_summary")
    @patch("main.get_summary")
    @patch("main.record_cycle")
    @patch("main.run_trading_cycle")
    def test_trading_job_does_not_call_alert_cycle_summary_when_aborted(
        self,
        mock_run_trading_cycle: MagicMock,
        mock_record_cycle: MagicMock,
        mock_get_summary: MagicMock,
        mock_alert_cycle_summary: MagicMock,
        mock_t212_client: MagicMock,
        mock_send_alert: MagicMock,
    ) -> None:
        result = {"status": "aborted", "reason": "pipeline_empty", "orders": []}
        mock_run_trading_cycle.return_value = result
        mock_get_summary.return_value = {"is_killed": False, "loss_pct": 0.0}

        trading_job()

        mock_alert_cycle_summary.assert_not_called()


if __name__ == "__main__":
    unittest.main()
