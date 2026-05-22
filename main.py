#!/usr/bin/env python3
"""Main entry point for trading bot."""

import signal
import sys
from threading import Event
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from broker.t212_client import T212Client
from broker.trading_loop import TradingLoop, run_trading_cycle
from config.logger import get_logger
from config.settings import PAPER_STARTING_CASH, TRADING_MODE, get_startup_banner
from monitoring.journal import record_cycle
from monitoring.telegram_alert import alert_cycle_detail, alert_cycle_summary, send_alert
from risk.daily_loss_tracker import get_summary

logger = get_logger(__name__)
NY_TZ = pytz.timezone("America/New_York")

# Global reference for clean shutdown
trading_loop = None
client = None
scheduler = None
shutdown_event = Event()


def trading_job():
    """Execute one trading cycle."""
    global trading_loop

    # Backward-compatible path used by legacy tests.
    if trading_loop is None and client is not None:
        try:
            result = run_trading_cycle(client)
            record_cycle(result)

            status = str(result.get("status", ""))
            if status == "completed":
                alert_cycle_detail(result)

            get_summary()
        except Exception as exc:
            logger.exception("Legacy trading job failed: %s", exc)
            send_alert(f"❌ Trading cycle failed: {str(exc)[:100]}")
        return

    if trading_loop is None:
        logger.error("Trading loop not initialized")
        return

    logger.info("=" * 40)
    logger.info("Starting scheduled trading cycle")
    logger.info("=" * 40)

    try:
        result = trading_loop.run_cycle()

        # Send alert for kill switch activation
        if result.get("reason") == "kill_switch_active":
            send_alert("🔴 KILL SWITCH ACTIVE - Daily loss limit reached. Trading halted.")
        elif result.get("orders_executed", 0) > 0:
            send_alert(
                f"📊 Cycle complete: {result['orders_executed']} orders executed, {result.get('orders_approved', 0)} approved"
            )

    except Exception as exc:
        logger.exception("Trading job failed: %s", exc)
        send_alert(f"❌ Trading cycle failed: {str(exc)[:100]}")


def signal_handler(signum, frame):
    """Handle shutdown signals."""
    _ = frame
    if shutdown_event.is_set():
        return

    shutdown_event.set()
    logger.info("Received signal %s, shutting down...", signum)

    # Keep signal handling non-blocking and avoid network calls here.
    if scheduler and scheduler.running:
        try:
            scheduler.shutdown(wait=False)
        except Exception as exc:
            logger.warning("Scheduler shutdown from signal handler failed: %s", exc)


def main():
    """Main entry point."""
    global trading_loop, scheduler

    # Print startup banner
    print(get_startup_banner())

    # Setup signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Send startup alert
    mode_emoji = "📄" if TRADING_MODE == "paper" else "💰"
    send_alert(f"{mode_emoji} Trading bot started in {TRADING_MODE.upper()} mode")

    # Initialize trading loop
    logger.info(f"Initializing trading loop in {TRADING_MODE.upper()} mode")

    if TRADING_MODE == "paper":
        trading_loop = TradingLoop(
            mode="paper",
            starting_paper_cash=PAPER_STARTING_CASH,
            live_client=None,
        )
        logger.info(f"Paper mode active with £{PAPER_STARTING_CASH:.2f} starting cash")
    else:
        # Live mode - will need Trading 212 client
        from broker.t212_client import T212Client

        live_client = T212Client()
        trading_loop = TradingLoop(
            mode="live",
            starting_paper_cash=0,
            live_client=live_client,
        )
        logger.warning("LIVE MODE ACTIVE - Real trades will be placed!")
        send_alert("⚠️ LIVE MODE ACTIVE - Real money trading enabled")

    # Setup scheduler for US market hours (Eastern Time)
    scheduler = BackgroundScheduler(timezone=NY_TZ)

    # Schedule every 5 minutes from 9:35 AM to 3:55 PM Eastern, weekdays only
    scheduler.add_job(
        trading_job,
        trigger=CronTrigger(
            day_of_week="mon-fri",
            hour="9-15",
            minute="*/5",
            timezone=NY_TZ,
        ),
        id="trading_cycle",
    )

    # Also schedule market open reset at 9:30 AM
    scheduler.add_job(
        trading_loop.reset_daily,
        trigger=CronTrigger(
            day_of_week="mon-fri",
            hour=9,
            minute=30,
            timezone=NY_TZ,
        ),
        id="daily_reset",
    )

    logger.info("Scheduler configured with US market hours (Eastern Time)")
    logger.info("Market hours: 9:35 AM - 3:55 PM ET, every 5 minutes")
    logger.info("Daily reset at 9:30 AM ET")

    # Send scheduler start alert
    send_alert("⏰ Trading bot scheduler started - waiting for market hours")

    scheduler.start()

    try:
        while not shutdown_event.is_set():
            shutdown_event.wait(timeout=1)
    except KeyboardInterrupt:
        shutdown_event.set()
        logger.info("Keyboard interrupt received")
    finally:
        if scheduler.running:
            scheduler.shutdown(wait=False)
        logger.info("Bot stopped by user")
        send_alert("🛑 Trading bot stopped")


if __name__ == "__main__":
    main()
