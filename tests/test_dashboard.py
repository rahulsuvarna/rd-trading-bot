import sqlite3
from pathlib import Path

from scripts.dashboard import TradingDashboard


def _create_journal(db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS cycles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            status TEXT NOT NULL,
            reason TEXT,
            free_cash REAL,
            signals TEXT,
            orders_executed INTEGER,
            orders_approved INTEGER
        )
        """
    )
    conn.commit()
    conn.close()


def _insert_cycle(db_path: Path, timestamp: str, signals: str, orders_executed: int) -> None:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO cycles (timestamp, status, reason, free_cash, signals, orders_executed, orders_approved)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (timestamp, "completed", None, 0.0, signals, orders_executed, orders_executed),
    )
    conn.commit()
    conn.close()


def test_load_journal_returns_false_when_missing(tmp_path: Path):
    db_path = tmp_path / "journal.db"
    dashboard = TradingDashboard(db_path=db_path)

    assert dashboard.load_journal() is False


def test_empty_journal_loads_default_state(tmp_path: Path):
    db_path = tmp_path / "journal.db"
    _create_journal(db_path)

    dashboard = TradingDashboard(db_path=db_path)
    assert dashboard.load_journal() is True
    assert dashboard.positions == {}
    assert dashboard.cash == dashboard.starting_cash


def test_position_averaging_after_multiple_buys(tmp_path: Path):
    db_path = tmp_path / "journal.db"
    _create_journal(db_path)

    _insert_cycle(
        db_path,
        "2026-05-21T10:00:00",
        '{"AAPL_US_EQ": {"signal": "BUY", "price": 100.0, "shares": 2.0, "executed": true}}',
        1,
    )
    _insert_cycle(
        db_path,
        "2026-05-21T10:05:00",
        '{"AAPL_US_EQ": {"signal": "BUY", "price": 120.0, "shares": 1.0, "executed": true}}',
        1,
    )

    dashboard = TradingDashboard(db_path=db_path)
    dashboard.load_journal()

    pos = dashboard.positions["AAPL_US_EQ"]
    assert pos["shares"] == 3.0
    assert pos["avg_cost"] == 106.666667


def test_sells_reduce_positions_correctly(tmp_path: Path):
    db_path = tmp_path / "journal.db"
    _create_journal(db_path)

    _insert_cycle(
        db_path,
        "2026-05-21T10:00:00",
        '{"AAPL_US_EQ": {"signal": "BUY", "price": 100.0, "shares": 3.0, "executed": true}}',
        1,
    )
    _insert_cycle(
        db_path,
        "2026-05-21T10:05:00",
        '{"AAPL_US_EQ": {"signal": "SELL", "price": 110.0, "shares": 1.0, "executed": true}}',
        1,
    )

    dashboard = TradingDashboard(db_path=db_path)
    dashboard.load_journal()

    pos = dashboard.positions["AAPL_US_EQ"]
    assert pos["shares"] == 2.0


def test_cash_balance_updates_after_trades(tmp_path: Path):
    db_path = tmp_path / "journal.db"
    _create_journal(db_path)

    _insert_cycle(
        db_path,
        "2026-05-21T10:00:00",
        '{"AAPL_US_EQ": {"signal": "BUY", "price": 100.0, "shares": 2.0, "executed": true}}',
        1,
    )
    _insert_cycle(
        db_path,
        "2026-05-21T10:05:00",
        '{"AAPL_US_EQ": {"signal": "SELL", "price": 110.0, "shares": 1.0, "executed": true}}',
        1,
    )

    dashboard = TradingDashboard(db_path=db_path)
    dashboard.load_journal()

    expected_cash = dashboard.starting_cash - 200.0 + 110.0
    assert dashboard.cash == expected_cash
