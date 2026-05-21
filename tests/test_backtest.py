from __future__ import annotations

import pandas as pd
import pytest

from scripts.backtest import (
    calculate_metrics,
    fetch_ohlcv,
    generate_signal_from_row,
    run_backtest,
    simulate_backtest,
)


def test_fetch_historical_data_non_empty():
    data = fetch_ohlcv(symbol="SPY", period="5d", interval="5m")
    if data.empty:
        pytest.skip("No network/data available from yfinance during test run")
    assert not data.empty


def test_signal_generation_outputs_valid_actions():
    assert generate_signal_from_row(close=95.0, rsi_14=30.0, vwap=100.0) == "BUY"
    assert generate_signal_from_row(close=105.0, rsi_14=70.0, vwap=100.0) == "SELL"
    assert generate_signal_from_row(close=100.0, rsi_14=50.0, vwap=100.0) == "HOLD"


def test_simulation_no_trades_when_cash_zero():
    data = fetch_ohlcv(symbol="SPY", period="5d", interval="5m")
    if data.empty:
        pytest.skip("No network/data available from yfinance during test run")

    equity_df, trades, metrics = simulate_backtest(data, initial_capital=0.0)
    assert not equity_df.empty
    assert trades == []
    assert metrics["number_of_trades"] == 0


def test_metrics_value_ranges():
    data = fetch_ohlcv(symbol="SPY", period="5d", interval="5m")
    if data.empty:
        pytest.skip("No network/data available from yfinance during test run")

    _, _, metrics = simulate_backtest(data, initial_capital=1000.0)

    assert -100.0 <= metrics["total_return_pct"] <= 1000.0
    assert 0.0 <= metrics["max_drawdown_pct"] <= 100.0
    assert 0.0 <= metrics["win_rate_pct"] <= 100.0
    assert metrics["number_of_trades"] >= 0
    assert metrics["profit_factor"] >= 0.0


def test_end_to_end_backtest_one_day_runs_without_error(tmp_path):
    data = fetch_ohlcv(symbol="SPY", period="5d", interval="5m")
    if data.empty:
        pytest.skip("No network/data available from yfinance during test run")

    last_day = data.index[-1].date()
    one_day = data[data.index.date == last_day]
    if one_day.empty:
        pytest.skip("Could not isolate one trading day from fetched data")

    equity_df, trades, _ = simulate_backtest(one_day, initial_capital=1000.0)
    assert not equity_df.empty
    assert isinstance(trades, list)

    result = run_backtest(
        symbol="SPY",
        period="1d",
        interval="5m",
        initial_capital=1000.0,
        output_csv=str(tmp_path / "equity.csv"),
    )
    assert "metrics" in result
    assert "equity_curve_csv" in result


def test_calculate_metrics_empty_curve():
    metrics = calculate_metrics(pd.Series(dtype=float), [], initial_capital=1000.0)
    assert metrics["total_return_pct"] == pytest.approx(0.0)
    assert metrics["max_drawdown_pct"] == pytest.approx(0.0)


def _raw_bars() -> pd.DataFrame:
    idx = pd.date_range("2026-01-01", periods=3, freq="5min", tz="UTC")
    return pd.DataFrame(
        {
            "Open": [100.0, 101.0, 102.0],
            "High": [101.0, 102.0, 103.0],
            "Low": [99.0, 100.0, 101.0],
            "Close": [100.5, 101.5, 102.5],
            "Volume": [1000.0, 1200.0, 1100.0],
        },
        index=idx,
    )


def test_fetch_clamps_intraday_period_and_warns(monkeypatch, capsys):
    from scripts import backtest as backtest_module

    calls: list[tuple[str, str]] = []

    class FakeTicker:
        def __init__(self, _symbol: str):
            # Test double: symbol value is irrelevant for deterministic history responses.
            pass

        def history(self, period: str, interval: str, auto_adjust: bool = False):
            calls.append((period, interval))
            return _raw_bars()

    monkeypatch.setattr(backtest_module.yf, "Ticker", FakeTicker)

    data = backtest_module.fetch_ohlcv(symbol="SPY", period="6mo", interval="5m")
    out = capsys.readouterr().out

    assert "Interval 5m limited to 60 days by Yahoo. Using last 60 days instead of 6mo." in out
    assert calls == [("60d", "5m")]
    assert not data.empty
    assert data.attrs.get("used_period") == "60d"
    assert data.attrs.get("used_interval") == "5m"


def test_fetch_falls_back_to_60m_then_1d(monkeypatch):
    from scripts import backtest as backtest_module

    calls: list[tuple[str, str]] = []

    class FakeTicker:
        def __init__(self, _symbol: str):
            # Test double: symbol value is irrelevant for deterministic history responses.
            pass

        def history(self, period: str, interval: str, auto_adjust: bool = False):
            calls.append((period, interval))
            if interval in {"5m", "60m"}:
                return pd.DataFrame()
            return _raw_bars()

    monkeypatch.setattr(backtest_module.yf, "Ticker", FakeTicker)

    data = backtest_module.fetch_ohlcv(symbol="SPY", period="3mo", interval="5m")

    assert calls == [("60d", "5m"), ("3mo", "60m"), ("3mo", "1d")]
    assert not data.empty
    assert data.attrs.get("used_interval") == "1d"


def test_fetch_force_interval_skips_fallback(monkeypatch):
    from scripts import backtest as backtest_module

    calls: list[tuple[str, str]] = []

    class FakeTicker:
        def __init__(self, _symbol: str):
            # Test double: symbol value is irrelevant for deterministic history responses.
            pass

        def history(self, period: str, interval: str, auto_adjust: bool = False):
            calls.append((period, interval))
            return pd.DataFrame()

    monkeypatch.setattr(backtest_module.yf, "Ticker", FakeTicker)

    with pytest.raises(RuntimeError, match="No market data returned for SPY after trying"):
        backtest_module.fetch_ohlcv(
            symbol="SPY",
            period="3mo",
            interval="5m",
            force_interval=True,
        )

    assert calls == [("60d", "5m")]
