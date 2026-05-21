"""Unit tests for OrderExecutor."""

import pytest

from broker.order_executor import OrderExecutor
from broker.simulated_account import SimulatedAccount


class TestOrderExecutorPaperMode:
    """Tests for paper mode execution."""

    def test_paper_mode_initialization(self):
        """Test paper mode creates SimulatedAccount."""
        executor = OrderExecutor(mode="paper", starting_paper_cash=500.0)
        assert executor.mode == "paper"
        assert executor.paper_account is not None
        assert isinstance(executor.paper_account, SimulatedAccount)
        assert executor.paper_account.get_cash() == pytest.approx(500.0)

    def test_paper_mode_get_cash(self):
        """Test get_available_cash returns paper account cash."""
        executor = OrderExecutor(mode="paper", starting_paper_cash=1000.0)
        assert executor.get_available_cash() == pytest.approx(1000.0)

    def test_paper_mode_get_positions_initial_empty(self):
        """Test get_positions returns empty dict initially."""
        executor = OrderExecutor(mode="paper")
        assert executor.get_positions() == {}

    def test_paper_mode_buy_execution(self):
        """Test executing a buy in paper mode."""
        executor = OrderExecutor(mode="paper", starting_paper_cash=1000.0)
        result = executor.execute_order("AAPL_US_EQ", "BUY", 500.0, 150.0)
        assert result["executed"] is True
        assert result["ticker"] == "AAPL_US_EQ"
        assert result["cost"] == pytest.approx(500.0)
        assert executor.get_available_cash() == pytest.approx(500.0)

    def test_paper_mode_sell_execution(self):
        """Test executing a sell in paper mode."""
        executor = OrderExecutor(mode="paper", starting_paper_cash=1000.0)
        # First buy
        buy_result = executor.execute_order("AAPL_US_EQ", "BUY", 500.0, 150.0)
        # Then sell all shares
        shares_held = buy_result["shares"]
        result = executor.execute_order("AAPL_US_EQ", "SELL", shares_held, 155.0)
        assert result["executed"] is True
        assert result["ticker"] == "AAPL_US_EQ"

    def test_paper_mode_unknown_signal(self):
        """Test unknown signal returns failure."""
        executor = OrderExecutor(mode="paper")
        result = executor.execute_order("AAPL_US_EQ", "HOLD", 100.0, 150.0)
        assert result["executed"] is False
        assert "Unknown" in result["reason"]

    def test_paper_mode_reset(self):
        """Test resetting paper account."""
        executor = OrderExecutor(mode="paper", starting_paper_cash=1000.0)
        executor.execute_order("AAPL_US_EQ", "BUY", 500.0, 150.0)
        executor.reset_paper_account(starting_cash=2000.0)
        assert executor.get_available_cash() == pytest.approx(2000.0)
        assert executor.get_positions() == {}


class TestOrderExecutorLiveMode:
    """Tests for live mode (returns NotImplemented)."""

    def test_live_mode_initialization(self):
        """Test live mode initializes without paper account."""
        executor = OrderExecutor(mode="live", live_client=None)
        assert executor.mode == "live"
        assert executor.paper_account is None

    def test_live_mode_get_cash_raises_without_client(self):
        """Test get_available_cash raises without live client."""
        executor = OrderExecutor(mode="live", live_client=None)
        with pytest.raises(RuntimeError, match="Live client not provided"):
            executor.get_available_cash()

    def test_live_mode_execute_returns_not_implemented(self):
        """Test execute_order returns not implemented in live mode."""
        executor = OrderExecutor(mode="live")
        result = executor.execute_order("AAPL_US_EQ", "BUY", 500.0, 150.0)
        assert result["executed"] is False
        assert "not implemented" in result["reason"].lower()
