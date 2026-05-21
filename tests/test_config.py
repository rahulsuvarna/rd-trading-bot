import unittest
from pathlib import Path

from config import settings
from config.logger import get_logger


class TestConfig(unittest.TestCase):
    def test_settings_loads_without_errors(self) -> None:
        self.assertIsNotNone(settings)

    def test_is_paper_mode_is_boolean(self) -> None:
        self.assertIsInstance(settings.IS_PAPER_MODE, bool)

    def test_max_risk_per_trade_between_zero_and_one(self) -> None:
        self.assertGreater(settings.MAX_RISK_PER_TRADE, 0)
        self.assertLess(settings.MAX_RISK_PER_TRADE, 1)

    def test_logger_creates_log_file(self) -> None:
        logger = get_logger("test_logger")
        logger.info("Test log line")

        log_path = Path(settings.LOGS_DIR) / "bot.log"
        self.assertTrue(log_path.exists())


if __name__ == "__main__":
    unittest.main()
