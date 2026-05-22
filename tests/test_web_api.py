import json
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from web_api.main import app


def _create_db(db_path: Path) -> None:
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
            orders TEXT,
            orders_executed INTEGER,
            orders_approved INTEGER
        )
        """
    )
    conn.commit()
    conn.close()


def _insert_cycle(
    db_path: Path,
    timestamp: str,
    free_cash: float,
    orders: list[dict],
    signals: dict | None = None,
) -> None:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO cycles (timestamp, status, reason, free_cash, signals, orders, orders_executed, orders_approved)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            timestamp,
            "completed",
            None,
            free_cash,
            json.dumps(signals or {}),
            json.dumps(orders),
            sum(1 for order in orders if order.get("executed", True)),
            len(orders),
        ),
    )
    conn.commit()
    conn.close()


@patch("web_api.main._fetch_current_prices", return_value={})
def test_api_endpoints_structure(mock_prices):
    client = TestClient(app)

    state = client.get("/api/state")
    assert state.status_code == 200
    for key in [
        "mode",
        "cash",
        "positions_count",
        "portfolio_value",
        "unrealized_pnl",
        "today_pnl",
        "kill_switch_active",
    ]:
        assert key in state.json()

    positions = client.get("/api/positions")
    assert positions.status_code == 200
    assert isinstance(positions.json(), list)

    trades = client.get("/api/trades?limit=10")
    assert trades.status_code == 200
    assert isinstance(trades.json(), list)

    eq = client.get("/api/equity_history")
    assert eq.status_code == 200
    assert "timestamps" in eq.json() and "values" in eq.json()

    cycles = client.get("/api/cycle_history")
    assert cycles.status_code == 200
    assert isinstance(cycles.json(), list)


def test_state_cash_from_journal(tmp_path: Path):
    db_path = tmp_path / "journal.db"
    _create_db(db_path)
    _insert_cycle(
        db_path,
        "2026-05-21T10:00:00+00:00",
        777.0,
        [
            {
                "executed": True,
                "action": "BUY",
                "ticker": "AAPL_US_EQ",
                "shares": 1.0,
                "price": 100.0,
                "cost": 100.0,
            }
        ],
    )

    with patch("web_api.main.JOURNAL_PATH", db_path), patch(
        "web_api.main._fetch_current_prices", return_value={}
    ):
        client = TestClient(app)
        response = client.get("/api/state")
        assert response.status_code == 200
        assert response.json()["cash"] == pytest.approx(777.0)


def test_positions_aggregated_from_orders(tmp_path: Path):
    db_path = tmp_path / "journal.db"
    _create_db(db_path)

    _insert_cycle(
        db_path,
        "2026-05-21T10:00:00+00:00",
        900.0,
        [
            {
                "executed": True,
                "action": "BUY",
                "ticker": "AAPL_US_EQ",
                "shares": 1.0,
                "price": 100.0,
                "cost": 100.0,
            }
        ],
    )
    _insert_cycle(
        db_path,
        "2026-05-21T10:05:00+00:00",
        680.0,
        [
            {
                "executed": True,
                "side": "BUY",
                "ticker": "AAPL_US_EQ",
                "quantity": 2.0,
                "price": 110.0,
                "value": 220.0,
            }
        ],
    )

    with patch("web_api.main.JOURNAL_PATH", db_path), patch(
        "web_api.main._fetch_current_prices", return_value={"AAPL_US_EQ": 120.0}
    ):
        client = TestClient(app)
        response = client.get("/api/positions")
        assert response.status_code == 200
        payload = response.json()
        assert len(payload) == 1
        assert payload[0]["ticker"] == "AAPL"
        assert payload[0]["shares"] == pytest.approx(3.0)
        assert payload[0]["avg_cost"] == pytest.approx((100.0 + 220.0) / 3.0)


def test_trades_non_empty_when_orders_exist(tmp_path: Path):
    db_path = tmp_path / "journal.db"
    _create_db(db_path)

    _insert_cycle(
        db_path,
        "2026-05-21T10:00:00+00:00",
        900.0,
        [
            {
                "executed": True,
                "action": "BUY",
                "ticker": "MSFT_US_EQ",
                "shares": 1.0,
                "price": 100.0,
                "amount": 100.0,
            }
        ],
    )
    _insert_cycle(
        db_path,
        "2026-05-21T10:05:00+00:00",
        1015.0,
        [
            {
                "executed": True,
                "action": "SELL",
                "ticker": "MSFT_US_EQ",
                "shares": 1.0,
                "price": 115.0,
                "proceeds": 115.0,
                "cost_basis": 100.0,
            }
        ],
    )

    with patch("web_api.main.JOURNAL_PATH", db_path), patch(
        "web_api.main._fetch_current_prices", return_value={}
    ):
        client = TestClient(app)
        response = client.get("/api/trades?limit=10")
        assert response.status_code == 200
        payload = response.json()
        assert len(payload) == 2
        assert {trade["action"] for trade in payload} == {"BUY", "SELL"}
        assert all("T" in trade["timestamp"] for trade in payload)
        assert all(trade["ticker"] == "MSFT" for trade in payload)
        assert all("value" in trade for trade in payload)
        assert payload[0]["value"] == pytest.approx(115.0)
        assert payload[1]["value"] == pytest.approx(100.0)


def test_missing_journal_graceful():
    missing_path = Path("c:/definitely_missing/journal.db")

    with patch("web_api.main.JOURNAL_PATH", missing_path), patch(
        "web_api.main._fetch_current_prices", return_value={}
    ):
        client = TestClient(app)
        response = client.get("/api/state")
        assert response.status_code == 200
        payload = response.json()
        assert payload["positions_count"] == 0
