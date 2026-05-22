# Trading Bot Architecture

## Overview
This application is an intraday trading bot scaffold focused on safe orchestration and observability. It is currently designed to fetch market data, generate signals, apply risk controls, simulate or gate execution, and persist each cycle outcome.

The system is modular and intentionally staged:
- Data ingestion and indicator enrichment
- Signal generation
- Risk approval and kill-switch enforcement
- Execution abstraction with paper and live branches
- Monitoring via SQLite journal and Telegram alerts
- Time-based scheduling during US market hours

## High-Level Runtime Flow
The runtime entry point is main.py. A recurring scheduler triggers one trading cycle every 5 minutes during configured US market hours.

Startup sequence:
1. Print startup banner
2. Initialise journal database
3. Initialise daily loss tracker with starting capital
4. Construct one Trading 212 client instance
5. Send startup Telegram alert
6. Start scheduler

Per-cycle sequence:
1. Fetch free cash from broker client
2. Run market data pipeline for the watchlist
3. Generate per-ticker signals
4. For each signal, run risk gate then execution step
5. Persist cycle result to journal
6. Send cycle summary alert when completed
7. Send kill-switch alert when risk state is halted

## Module Responsibilities

### Configuration Layer
- config/settings.py
  - Loads environment variables
  - Exposes runtime constants
  - Provides path constants and startup banner
- config/logger.py
  - Central logger factory
  - Console plus rotating file logging
- config/watchlist.py
  - Watchlist symbols and market data interval settings

### Broker Layer
- broker/t212_client.py
  - Read-only Trading 212 account and positions API client
  - Auth header handling and timeout protection
- broker/order_executor.py
  - Execution abstraction
  - Paper mode simulation and live mode guardrail
- broker/trading_loop.py
  - Main cycle orchestrator for cash check, pipeline, signals, risk, execution

### Data Layer
- data/price_fetcher.py
  - Fetches OHLCV bars for one ticker
  - Normalizes and validates returned columns
- data/indicators.py
  - Adds EMA20, RSI14, and VWAP
  - Removes warmup rows with missing indicators
- data/pipeline.py
  - Runs fetch plus indicators for all watchlist tickers

### Strategy Layer
- strategies/vwap_reversion.py
  - Single-candle VWAP plus RSI rule engine
  - BUY, SELL, HOLD output
- strategies/signal_runner.py
  - Applies strategy function across pipeline outputs

### Risk Layer
- risk/position_sizer.py
  - Converts approved signal plus capital into trade amount
  - Enforces minimum trade amount
- risk/daily_loss_tracker.py
  - In-memory daily capital state and kill switch logic
- risk/risk_gate.py
  - Ordered approval logic:
    - kill switch
    - HOLD short-circuit
    - trade amount viability
    - approval

### Monitoring Layer
- monitoring/journal.py
  - SQLite persistence of cycle outcomes in logs/journal.db
  - Recent cycle retrieval for inspection
- monitoring/telegram_alert.py
  - Telegram message delivery and alert templates

### Application Entry
- main.py
  - Startup orchestration
  - Scheduler creation and lifecycle management
  - Keyboard interrupt shutdown handling

## Core Data Contracts

### Trading cycle result
Returned by broker/trading_loop.py:
- status: completed or aborted
- free_cash: float when available
- reason: abort reason when aborted
- signals: map of ticker to signal
- orders: list of execution result objects

### Risk decision
Produced by risk/risk_gate.py:
- approved: bool
- signal: string
- trade_amount: float
- reason: string

### Execution result
Produced by broker/order_executor.py:
- executed: bool
- mode: paper or live
- signal: string
- trade_amount: float
- note: explanation or mode detail

### Journal row
Persisted by monitoring/journal.py:
- timestamp
- status
- reason
- free_cash
- signals as JSON text
- orders_executed count
- orders_approved count

## Scheduler Design
The scheduler uses APScheduler BlockingScheduler with America/New_York timezone and cron schedule constrained to weekdays and market session windows.

Intent:
- Trigger every 5 minutes
- Start from 09:35 ET
- Stop at 16:00 ET window boundaries based on cron expression

## Failure Handling Philosophy
The bot favors safe failure modes:
- Data fetch failures return None and skip processing
- Pipeline empty state aborts cycle cleanly
- Risk gate blocks on kill switch or invalid sizing
- Live execution branch remains explicitly non-operational until implemented
- Telegram and broker network failures degrade gracefully via logging and False returns

## Testing Strategy
The test suite is split by module with focused responsibilities:
- Unit tests for each layer
- Mocked external dependencies for broker and Telegram
- Synthetic data for strategy and pipeline logic where possible
- No real API dependency in unit tests

Key tests include:
- Data pipeline, indicators, and signal generation
- Risk gate and loss tracker behavior
- Order execution mode switching
- Trading loop orchestration
- Journal persistence and retrieval
- Main trading job behavior in isolation

## External Integrations
- Trading 212 Public API via requests
- Yahoo Finance market data via yfinance
- Technical indicators via ta
- Telegram Bot API for operational alerts
- SQLite for local durable journaling

## Current State and Next Step
Current implementation is production-leaning for orchestration and observability, with execution safety rails in place. The major remaining step is implementing live order placement in broker/order_executor.py with strict idempotency, validation, and post-trade reconciliation.
