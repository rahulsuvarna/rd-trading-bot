"""Tests for configuration settings."""

import os
from unittest.mock import patch

import pytest


class TestSettings:
    """Test configuration settings loading."""

    def test_trading_mode_default_paper(self):
        """Test TRADING_MODE defaults to 'paper'."""
        with patch.dict(os.environ, {}, clear=True):
            # Force reload of settings module
            import importlib
            import config.settings

            importlib.reload(config.settings)
            assert config.settings.TRADING_MODE == "paper"

    def test_trading_mode_reads_from_env(self):
        """Test TRADING_MODE reads from environment."""
        with patch.dict(
            os.environ,
            {"TRADING_MODE": "live", "TRADING212_API_KEY": "test-key"},
            clear=True,
        ):
            import importlib
            import config.settings

            importlib.reload(config.settings)
            assert config.settings.TRADING_MODE == "live"

    def test_paper_starting_cash_default(self):
        """Test PAPER_STARTING_CASH defaults to 1000.0."""
        with patch.dict(os.environ, {}, clear=True):
            import importlib
            import config.settings

            importlib.reload(config.settings)
            assert config.settings.PAPER_STARTING_CASH == pytest.approx(1000.0)

    def test_paper_starting_cash_reads_from_env(self):
        """Test PAPER_STARTING_CASH reads from environment."""
        with patch.dict(os.environ, {"PAPER_STARTING_CASH": "2500.50"}, clear=True):
            import importlib
            import config.settings

            importlib.reload(config.settings)
            assert config.settings.PAPER_STARTING_CASH == pytest.approx(2500.50)

    def test_invalid_trading_mode_raises_error(self):
        """Test invalid TRADING_MODE raises ValueError."""
        with patch.dict(os.environ, {"TRADING_MODE": "invalid"}, clear=True):
            import importlib
            import config.settings

            with pytest.raises(ValueError, match="Invalid TRADING_MODE"):
                importlib.reload(config.settings)

    def test_watchlist_default_returns_five_symbols(self):
        """Test WATCHLIST_SYMBOLS defaults to five symbols."""
        with patch.dict(
            os.environ,
            {"WATCHLIST": "SPY_US_EQ,QQQ_US_EQ,AAPL_US_EQ,MSFT_US_EQ,NVDA_US_EQ"},
            clear=True,
        ):
            import importlib
            import config.settings

            importlib.reload(config.settings)
            assert len(config.settings.WATCHLIST_SYMBOLS) == 5

    def test_watchlist_reads_from_env(self):
        """Test WATCHLIST_SYMBOLS reads comma-separated values from env."""
        with patch.dict(
            os.environ,
            {"WATCHLIST": "SPY_US_EQ,MSFT_US_EQ"},
            clear=True,
        ):
            import importlib
            import config.settings

            importlib.reload(config.settings)
            assert config.settings.WATCHLIST_SYMBOLS == ["SPY_US_EQ", "MSFT_US_EQ"]

    def test_watchlist_empty_raises_error(self):
        """Test empty WATCHLIST value raises ValueError."""
        with patch.dict(os.environ, {"WATCHLIST": "   ,   "}, clear=True):
            import importlib
            import config.settings

            with pytest.raises(ValueError, match="WATCHLIST must contain at least one symbol"):
                importlib.reload(config.settings)

    def test_watchlist_strips_whitespace(self):
        """Test WATCHLIST_SYMBOLS strips surrounding whitespace."""
        with patch.dict(
            os.environ,
            {"WATCHLIST": " SPY_US_EQ , QQQ_US_EQ ,  MSFT_US_EQ  "},
            clear=True,
        ):
            import importlib
            import config.settings

            importlib.reload(config.settings)
            assert config.settings.WATCHLIST_SYMBOLS == [
                "SPY_US_EQ",
                "QQQ_US_EQ",
                "MSFT_US_EQ",
            ]
