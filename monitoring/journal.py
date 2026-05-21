import json
import sqlite3
from datetime import datetime, timezone

from config.logger import get_logger
from config.settings import LOGS_DIR

JOURNAL_PATH = LOGS_DIR / "journal.db"


def initialise_journal() -> None:
    logger = get_logger(__name__)
    connection = sqlite3.connect(JOURNAL_PATH)
    cursor = connection.cursor()

    cursor.execute(
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

    # Migrate existing databases that pre-date the orders column.
    existing_columns = {row[1] for row in cursor.execute("PRAGMA table_info(cycles)").fetchall()}
    if "orders" not in existing_columns:
        cursor.execute("ALTER TABLE cycles ADD COLUMN orders TEXT")

    connection.commit()
    connection.close()
    logger.info("Journal initialised at %s", JOURNAL_PATH)


def record_cycle(cycle_result: dict) -> None:
    logger = get_logger(__name__)

    timestamp = datetime.now(timezone.utc).isoformat()
    status = cycle_result["status"]
    reason = cycle_result.get("reason", None)
    free_cash = cycle_result.get("free_cash", None)
    signals = json.dumps(cycle_result.get("signals", {}))

    orders = cycle_result.get("orders", [])
    orders_json = json.dumps(orders)
    orders_executed = sum(1 for order in orders if order.get("executed", False))

    rejection_reasons = {"kill_switch_active", "signal_is_hold", "trade_amount_too_small"}
    orders_approved = sum(
        1 for order in orders if order.get("note") not in rejection_reasons
    )

    connection = sqlite3.connect(JOURNAL_PATH)
    cursor = connection.cursor()

    cursor.execute(
        """
        INSERT INTO cycles (timestamp, status, reason, free_cash, signals, orders, orders_executed, orders_approved)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (timestamp, status, reason, free_cash, signals, orders_json, orders_executed, orders_approved),
    )

    connection.commit()
    connection.close()

    logger.info(
        "JOURNAL | recorded cycle | status=%s | orders_executed=%d",
        status,
        orders_executed,
    )


def get_recent_cycles(limit: int = 10) -> list:
    connection = sqlite3.connect(JOURNAL_PATH)
    connection.row_factory = sqlite3.Row
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT * FROM cycles ORDER BY id DESC LIMIT ?
        """,
        (limit,),
    )

    rows = cursor.fetchall()
    connection.close()

    return [dict(row) for row in rows]
