import os

def parse_env_file(filepath):
    values = {}
    if not os.path.exists(filepath):
        return values
    with open(filepath, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '=' in line:
                key, val = line.split('=', 1)
                key = key.strip()
                val = val.split('#')[0].strip() # remove comments
                if key not in values:
                    values[key] = []
                values[key].append(val)
    return values

def get_best_value(key, env_values, default_value):
    if key in env_values:
        occurrences = env_values[key]
        non_empty = [v for v in occurrences if v]
        if non_empty:
            return non_empty[-1]
        else:
            return occurrences[-1]
    return default_value

defaults = {
    'TRADING212_API_KEY': '',
    'TRADING212_API_SECRET': '',
    'TRADING_MODE': 'paper',
    'ENV': 'sandbox',
    'DATA_PROVIDER': 'yahoo',
    'ALPACA_API_KEY': '',
    'ALPACA_SECRET_KEY': '',
    'PAPER_STARTING_CASH': '1000.0',
    'MAX_RISK_PER_TRADE': '0.01',
    'DAILY_LOSS_LIMIT': '0.05',
    'MAX_CONCURRENT_POSITIONS': '5',
    'WATCHLIST': 'SPY_US_EQ,QQQ_US_EQ,AAPL_US_EQ,MSFT_US_EQ,NVDA_US_EQ',
    'TELEGRAM_BOT_TOKEN': '',
    'TELEGRAM_CHAT_ID': '',
    'LOG_LEVEL': 'INFO'
}

env_values = parse_env_file('.env')

final_values = {}
for key in defaults:
    final_values[key] = get_best_value(key, env_values, defaults[key])

template = """# ============================================================
# Trading Bot Environment
# ============================================================

# ------------------------------
# Trading 212 API (required for live mode)
# ------------------------------
TRADING212_API_KEY={TRADING212_API_KEY}
TRADING212_API_SECRET={TRADING212_API_SECRET}

# ------------------------------
# Runtime mode
# ------------------------------
# TRADING_MODE: paper | live
TRADING_MODE={TRADING_MODE}

# ENV controls Trading 212 base URL selection in code.
# Use sandbox for demo endpoint, live for production endpoint.
# ENV: sandbox | live
ENV={ENV}

# ------------------------------
# Market data provider
# ------------------------------
# DATA_PROVIDER: yahoo | alpaca
DATA_PROVIDER={DATA_PROVIDER}

# Alpaca keys are only needed when DATA_PROVIDER=alpaca
ALPACA_API_KEY={ALPACA_API_KEY}
ALPACA_SECRET_KEY={ALPACA_SECRET_KEY}

# ------------------------------
# Portfolio / risk
# ------------------------------
# Starting cash used in paper mode
PAPER_STARTING_CASH={PAPER_STARTING_CASH}

# Fraction of capital to risk per trade (e.g., 0.01 = 1%)
MAX_RISK_PER_TRADE={MAX_RISK_PER_TRADE}

# Daily loss limit fraction (e.g., 0.05 = 5%)
DAILY_LOSS_LIMIT={DAILY_LOSS_LIMIT}

# Maximum number of concurrent open positions
MAX_CONCURRENT_POSITIONS={MAX_CONCURRENT_POSITIONS}

# ------------------------------
# Watchlist
# ------------------------------
# Comma-separated Trading 212 tickers.
# Use _US_EQ suffix for US equities/ETFs.
WATCHLIST={WATCHLIST}

# ------------------------------
# Telegram alerts (optional)
# ------------------------------
TELEGRAM_BOT_TOKEN={TELEGRAM_BOT_TOKEN}
TELEGRAM_CHAT_ID={TELEGRAM_CHAT_ID}

# ------------------------------
# Logging
# ------------------------------
LOG_LEVEL={LOG_LEVEL}
"""

with open('.env', 'w') as f:
    f.write(template.format(**final_values))
