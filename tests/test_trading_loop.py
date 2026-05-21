"""Unit tests for TradingLoop."""

from unittest.mock import Mock, patch

import pytest

from broker.trading_loop import TradingLoop


class TestTradingLoopPaperMode:
    """Tests for paper mode trading loop."""

    def test_paper_mode_initialization(self):
        """Test paper mode initializes with executor."""
        with patch("broker.trading_loop.initialise"):
            loop = TradingLoop(mode="paper", starting_paper_cash=500.0)
        assert loop.mode == "paper"
        assert loop.executor is not None
        assert loop.get_available_cash() == pytest.approx(500.0)

    def test_paper_mode_get_cash_returns_from_executor(self):
        """Test get_available_cash returns executor cash."""
        with patch("broker.trading_loop.initialise"):
            loop = TradingLoop(mode="paper", starting_paper_cash=1000.0)
        assert loop.get_available_cash() == pytest.approx(1000.0)

    def test_paper_mode_get_positions_returns_empty_initial(self):
        """Test get_positions returns empty dict initially."""
        with patch("broker.trading_loop.initialise"):
            loop = TradingLoop(mode="paper")
        assert loop.get_positions() == {}

    def test_run_cycle_aborts_when_kill_switch_active(self):
        """Test cycle aborts when kill switch is active."""
        with patch("broker.trading_loop.initialise"), patch(
            "broker.trading_loop.is_trading_allowed", return_value=False
        ):
            loop = TradingLoop(mode="paper", starting_paper_cash=1000.0)
            result = loop.run_cycle()
            assert result["status"] == "aborted"
            assert result["reason"] == "kill_switch_active"

    def test_reset_daily(self):
        """Test resetting daily loss tracker."""
        with patch("broker.trading_loop.initialise"), patch(
            "broker.trading_loop.reset_daily_tracker"
        ) as mock_reset:
            loop = TradingLoop(mode="paper", starting_paper_cash=1000.0)
            loop.reset_daily()
            mock_reset.assert_called_once_with(1000.0)

    def test_reset_paper_account(self):
        """Test resetting paper account works."""
        with patch("broker.trading_loop.initialise"), patch(
            "broker.trading_loop.reset_daily_tracker"
        ):
            loop = TradingLoop(mode="paper", starting_paper_cash=1000.0)
            # Do a trade to change state
            loop.executor.execute_order("AAPL_US_EQ", "BUY", 500.0, 150.0)
            assert loop.get_available_cash() == pytest.approx(500.0)
            # Reset
            loop.reset_paper_account(starting_cash=2000.0)
            assert loop.get_available_cash() == pytest.approx(2000.0)
            assert loop.get_positions() == {}


class TestTradingLoopLiveMode:
    """Tests for live mode trading loop."""

    def test_live_mode_initialization(self):
        """Test live mode initializes without paper account."""
        with patch("broker.trading_loop.initialise"):
            loop = TradingLoop(mode="live", live_client=Mock())
        assert loop.mode == "live"
