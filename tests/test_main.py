import unittest
from unittest.mock import MagicMock, patch

import main
from main import trading_job


class TestMainTradingJob(unittest.TestCase):
    def setUp(self) -> None:
        self.mock_client = MagicMock()
        main.client = self.mock_client
        main.trading_loop = None

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
    @patch("main.alert_cycle_detail")
    @patch("main.get_summary")
    @patch("main.record_cycle")
    @patch("main.run_trading_cycle")
    def test_trading_job_calls_alert_cycle_detail_when_completed(
        self,
        mock_run_trading_cycle: MagicMock,
        mock_record_cycle: MagicMock,
        mock_get_summary: MagicMock,
        mock_alert_cycle_detail: MagicMock,
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

        mock_alert_cycle_detail.assert_called_once_with(result)

    @patch("main.send_alert")
    @patch("main.T212Client")
    @patch("main.alert_cycle_detail")
    @patch("main.get_summary")
    @patch("main.record_cycle")
    @patch("main.run_trading_cycle")
    def test_trading_job_does_not_call_alert_cycle_detail_when_aborted(
        self,
        mock_run_trading_cycle: MagicMock,
        mock_record_cycle: MagicMock,
        mock_get_summary: MagicMock,
        mock_alert_cycle_detail: MagicMock,
        mock_t212_client: MagicMock,
        mock_send_alert: MagicMock,
    ) -> None:
        result = {"status": "aborted", "reason": "pipeline_empty", "orders": []}
        mock_run_trading_cycle.return_value = result
        mock_get_summary.return_value = {"is_killed": False, "loss_pct": 0.0}

        trading_job()

        mock_alert_cycle_detail.assert_not_called()

    @patch("main.send_alert")
    @patch("main.alert_cycle_detail")
    def test_trading_job_uses_alert_cycle_detail_in_primary_loop(
        self,
        mock_alert_cycle_detail: MagicMock,
        mock_send_alert: MagicMock,
    ) -> None:
        main.client = None
        mock_loop = MagicMock()
        mock_loop.run_cycle.return_value = {
            "status": "completed",
            "orders_executed": 1,
            "orders_approved": 2,
            "signals": {"AAPL_US_EQ": {"signal": "BUY", "executed": True}},
            "free_cash": 900.0,
        }
        main.trading_loop = mock_loop

        trading_job()

        mock_alert_cycle_detail.assert_called_once()
        mock_send_alert.assert_not_called()

    @patch("main.send_alert")
    @patch("main.alert_cycle_detail")
    def test_trading_job_sends_abort_reason_in_primary_loop(
        self,
        mock_alert_cycle_detail: MagicMock,
        mock_send_alert: MagicMock,
    ) -> None:
        main.client = None
        mock_loop = MagicMock()
        mock_loop.run_cycle.return_value = {
            "status": "aborted",
            "reason": "no_pipeline_data",
            "free_cash": 123.45,
            "orders_executed": 0,
            "orders_approved": 0,
        }
        main.trading_loop = mock_loop

        trading_job()

        mock_alert_cycle_detail.assert_not_called()
        mock_send_alert.assert_called_once()
        sent_message = mock_send_alert.call_args[0][0]
        self.assertIn("Cycle aborted", sent_message)
        self.assertIn("no_pipeline_data", sent_message)


if __name__ == "__main__":
    unittest.main()
