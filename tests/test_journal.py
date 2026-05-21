import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from monitoring.journal import get_recent_cycles, initialise_journal, record_cycle


class TestJournal(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.mkdtemp()
        self.temp_db_path = Path(self.temp_dir) / "test_journal.db"
        self.patcher = patch(
            "monitoring.journal.JOURNAL_PATH", self.temp_db_path
        )
        self.patcher.start()

    def tearDown(self) -> None:
        self.patcher.stop()
        if self.temp_db_path.exists():
            self.temp_db_path.unlink()

    def test_initialise_journal_creates_database_file(self) -> None:
        initialise_journal()
        self.assertTrue(self.temp_db_path.exists())

    def test_record_cycle_with_completed_cycle(self) -> None:
        initialise_journal()

        cycle_result = {
            "status": "completed",
            "free_cash": 100.0,
            "signals": {"SPY": "BUY"},
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

        record_cycle(cycle_result)

        connection = sqlite3.connect(self.temp_db_path)
        cursor = connection.cursor()
        cursor.execute("SELECT COUNT(*) FROM cycles")
        count = cursor.fetchone()[0]
        connection.close()

        self.assertEqual(count, 1)

    def test_record_cycle_with_aborted_cycle(self) -> None:
        initialise_journal()

        cycle_result = {
            "status": "aborted",
            "reason": "no_free_cash",
        }

        record_cycle(cycle_result)

        connection = sqlite3.connect(self.temp_db_path)
        connection.row_factory = sqlite3.Row
        cursor = connection.cursor()
        cursor.execute("SELECT * FROM cycles WHERE id = 1")
        row = cursor.fetchone()
        connection.close()

        self.assertEqual(row["status"], "aborted")
        self.assertEqual(row["reason"], "no_free_cash")

    def test_get_recent_cycles_returns_most_recent_first(self) -> None:
        initialise_journal()

        cycle_1 = {
            "status": "aborted",
            "reason": "no_free_cash",
        }
        cycle_2 = {
            "status": "completed",
            "free_cash": 100.0,
            "signals": {"SPY": "BUY"},
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

        record_cycle(cycle_1)
        record_cycle(cycle_2)

        recent = get_recent_cycles(limit=10)

        self.assertEqual(len(recent), 2)
        self.assertEqual(recent[0]["status"], "completed")
        self.assertEqual(recent[1]["status"], "aborted")


if __name__ == "__main__":
    unittest.main()
