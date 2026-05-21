"""Configuration settings loaded from environment variables."""

import os
import re
from pathlib import Path

from dotenv import load_dotenv

# Load .env file from project root
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

# Trading 212 API Configuration
# Support both regular and ISA prefixed keys (prefer ISA for ISA account)
TRADING212_API_KEY = os.getenv("IISA_TRADING212_API_KEY") or os.getenv("TRADING212_API_KEY")
TRADING212_API_SECRET = os.getenv("IISA_TRADING212_API_SECRET") or os.getenv("TRADING212_API_SECRET")
TRADING212_ACCOUNT_TYPE = "ISA"  # Fixed for your use case

# Alpaca API (for data - optional, falls back to yfinance)
ALPACA_API_KEY = os.getenv("ALPACA_API_KEY")
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY")

# Telegram alerts - use first non-empty value (handle duplicates)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TELEGRAM_BOT_TOKEN:
    # Try reading from .env file manually to get the first non-empty value
    try:
        with open(env_path, "r", encoding="utf-8") as env_file:
            content = env_file.read()
            matches = re.findall(r"^TELEGRAM_BOT_TOKEN=(.+)$", content, re.MULTILINE)
            for match in matches:
                if match and match.strip() and "your_telegram_bot_token" not in match:
                    TELEGRAM_BOT_TOKEN = match.strip()
                    break
    except Exception:
        pass

TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
if not TELEGRAM_CHAT_ID:
    try:
        with open(env_path, "r", encoding="utf-8") as env_file:
            content = env_file.read()
            matches = re.findall(r"^TELEGRAM_CHAT_ID=(.+)$", content, re.MULTILINE)
            for match in matches:
                if match and match.strip() and "your_telegram_chat_id" not in match:
                    TELEGRAM_CHAT_ID = match.strip()
                    break
    except Exception:
        pass

# Environment (production/sandbox)
ENV = os.getenv("ENV", "sandbox").lower()

# Market data provider configuration
DATA_PROVIDER = os.getenv("DATA_PROVIDER", "yahoo").lower()
if DATA_PROVIDER not in ["yahoo", "alpaca"]:
    raise ValueError(
        f"Invalid DATA_PROVIDER: {DATA_PROVIDER}. Must be 'yahoo' or 'alpaca'"
    )

# Trading mode configuration
TRADING_MODE = os.getenv("TRADING_MODE", "paper").lower()
PAPER_STARTING_CASH = float(os.getenv("PAPER_STARTING_CASH", "1000.0"))

# Validate trading mode
if TRADING_MODE not in ["paper", "live"]:
    raise ValueError(f"Invalid TRADING_MODE: {TRADING_MODE}. Must be 'paper' or 'live'")

# Live mode safety check
if TRADING_MODE == "live":
    if not TRADING212_API_KEY or TRADING212_API_KEY == "your_trading212_api_key_here":
        raise ValueError("TRADING212_API_KEY required for live mode")
    print("⚠️  WARNING: Running in LIVE mode - real money will be traded!")
    print("   Starting cash from Trading 212: will be fetched from API")

# Risk limits
MAX_RISK_PER_TRADE = float(os.getenv("MAX_RISK_PER_TRADE", "0.01"))
DAILY_LOSS_LIMIT = float(os.getenv("DAILY_LOSS_LIMIT", "0.05"))  # 5% default

# Logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# Watchlist symbols (can be overridden by env)
WATCHLIST_SYMBOLS = [
    symbol.strip()
    for symbol in os.getenv(
        "WATCHLIST", "SPY_US_EQ,QQQ_US_EQ,AAPL_US_EQ,MSFT_US_EQ,NVDA_US_EQ"
    ).split(",")
    if symbol.strip()
]
if not WATCHLIST_SYMBOLS:
    raise ValueError("WATCHLIST must contain at least one symbol")

# Path constants
PROJECT_ROOT = Path(__file__).parent.parent
LOGS_DIR = PROJECT_ROOT / "logs"
DATA_DIR = PROJECT_ROOT / "data"
JOURNAL_DB = PROJECT_ROOT / "logs" / "journal.db"

# Ensure directories exist
LOGS_DIR.mkdir(exist_ok=True)


def get_startup_banner() -> str:
    """Return formatted startup banner with configuration."""
    # Check if Telegram is actually configured
    telegram_status = "✅ Configured" if (
        TELEGRAM_BOT_TOKEN
        and TELEGRAM_BOT_TOKEN not in ["", "your_telegram_bot_token_here"]
    ) else "❌ Not configured"

    banner = f"""
{'='*60}
  Trading Bot
{'='*60}
  Mode:           {TRADING_MODE.upper()}
  Paper Cash:     £{PAPER_STARTING_CASH:.2f} (if paper mode)
  Data Source:    {'Alpaca' if ALPACA_API_KEY else 'Yahoo Finance'}
  Watchlist:      {len(WATCHLIST_SYMBOLS)} symbols
  Log Level:      {LOG_LEVEL}
  Telegram:       {telegram_status}
{'='*60}
"""
    return banner


def print_startup_banner() -> None:
    """Backward-compatible startup banner printer."""
    print(get_startup_banner())


# For backward compatibility with existing code that expects WATCHLIST/IS_PAPER_MODE
WATCHLIST = WATCHLIST_SYMBOLS
IS_PAPER_MODE = TRADING_MODE == "paper"
