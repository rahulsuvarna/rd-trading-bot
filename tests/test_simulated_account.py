"""Unit tests for SimulatedAccount."""

import pytest

from broker.simulated_account import SimulatedAccount


class TestSimulatedAccount:
    """Test suite for SimulatedAccount."""

    def test_initialization(self):
        """Test account initializes with correct cash and empty positions."""
        account = SimulatedAccount(1000.0)
        assert account.get_cash() == 1000.0
        assert account.get_positions() == {}
        assert account.trade_history == []

    def test_get_cash_returns_current_balance(self):
        """Test get_cash returns correct value after operations."""
        account = SimulatedAccount(1000.0)
        account.execute_buy("AAPL_US_EQ", 100.0, 50.0)
        assert account.get_cash() == pytest.approx(900.0)

    def test_get_positions_returns_copy_not_reference(self):
        """Test modifying returned dict doesn't affect internal state."""
        account = SimulatedAccount(1000.0)
        account.execute_buy("AAPL_US_EQ", 100.0, 50.0)

        positions_copy = account.get_positions()
        positions_copy["AAPL_US_EQ"] = 999.0

        assert account.get_positions()["AAPL_US_EQ"] != 999.0

    def test_execute_buy_sufficient_cash(self):
        """Test buy succeeds when cash is enough."""
        account = SimulatedAccount(1000.0)
        result = account.execute_buy("AAPL_US_EQ", 100.0, 25.0)

        assert result["executed"] is True
        assert result["ticker"] == "AAPL_US_EQ"
        assert result["shares"] == 4.0
        assert result["cost"] == 100.0
        assert result["remaining_cash"] == pytest.approx(900.0)

    def test_execute_buy_insufficient_cash(self):
        """Test buy fails when cash is insufficient."""
        account = SimulatedAccount(100.0)
        result = account.execute_buy("AAPL_US_EQ", 150.0, 10.0)

        assert result["executed"] is False
        assert result["reason"] == "insufficient_cash"
        assert account.get_cash() == 100.0
        assert account.get_positions() == {}

    def test_execute_sell_sufficient_shares(self):
        """Test sell succeeds when shares are held."""
        account = SimulatedAccount(1000.0)
        account.execute_buy("AAPL_US_EQ", 100.0, 10.0)  # 10 shares

        result = account.execute_sell("AAPL_US_EQ", 4.0, 12.0)

        assert result["executed"] is True
        assert result["shares"] == 4.0
        assert result["proceeds"] == 48.0
        assert account.get_positions()["AAPL_US_EQ"] == pytest.approx(6.0)

    def test_execute_sell_insufficient_shares(self):
        """Test sell fails when not enough shares."""
        account = SimulatedAccount(1000.0)
        account.execute_buy("AAPL_US_EQ", 100.0, 10.0)  # 10 shares

        result = account.execute_sell("AAPL_US_EQ", 11.0, 10.0)

        assert result["executed"] is False
        assert result["reason"] == "insufficient_shares"
        assert account.get_positions()["AAPL_US_EQ"] == pytest.approx(10.0)

    def test_execute_sell_all_shares_removes_ticker(self):
        """Test selling all shares removes ticker from positions."""
        account = SimulatedAccount(1000.0)
        account.execute_buy("AAPL_US_EQ", 100.0, 10.0)  # 10 shares

        result = account.execute_sell("AAPL_US_EQ", 10.0, 11.0)

        assert result["executed"] is True
        assert "AAPL_US_EQ" not in account.get_positions()

    def test_reset_returns_to_fresh_state(self):
        """Test reset clears all trades and resets cash."""
        account = SimulatedAccount(1000.0)
        account.execute_buy("AAPL_US_EQ", 100.0, 10.0)
        account.execute_sell("AAPL_US_EQ", 5.0, 11.0)

        account.reset(starting_cash=500.0)

        assert account.get_cash() == 500.0
        assert account.get_positions() == {}
        assert account.trade_history == []

    def test_multiple_trades_same_ticker(self):
        """Test buy then sell then buy on same ticker works correctly."""
        account = SimulatedAccount(1000.0)

        buy_1 = account.execute_buy("AAPL_US_EQ", 100.0, 10.0)   # +10 shares
        sell_1 = account.execute_sell("AAPL_US_EQ", 4.0, 12.0)    # -4 shares
        buy_2 = account.execute_buy("AAPL_US_EQ", 60.0, 15.0)     # +4 shares

        assert buy_1["executed"] is True
        assert sell_1["executed"] is True
        assert buy_2["executed"] is True

        positions = account.get_positions()
        assert positions["AAPL_US_EQ"] == pytest.approx(10.0)
        assert account.get_cash() == pytest.approx(888.0)
        assert len(account.trade_history) == 3
