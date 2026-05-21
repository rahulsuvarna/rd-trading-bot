"""Telegram alert sending module."""

import requests

from config.logger import get_logger
from config.settings import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

logger = get_logger(__name__)


def _telegram_enabled() -> bool:
    """Check if Telegram credentials are configured."""
    return bool(
        TELEGRAM_BOT_TOKEN
        and TELEGRAM_BOT_TOKEN not in ["", "your_telegram_bot_token_here"]
        and TELEGRAM_CHAT_ID
        and TELEGRAM_CHAT_ID not in ["", "your_telegram_chat_id_here"]
    )


def send_alert(message: str) -> bool:
    """
    Send an alert via Telegram.

    Args:
        message: Message text to send

    Returns:
        True if sent successfully (or skipped due to no config), False on error
    """
    if not _telegram_enabled():
        logger.debug("Telegram not configured - skipping alert: %s", message[:50])
        return True

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
    }

    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            logger.info("TELEGRAM | alert sent: %s", message[:50])
            return True

        logger.warning("TELEGRAM | failed to send alert: %s", response.status_code)
        return False
    except Exception as exc:
        logger.warning("TELEGRAM | exception sending alert: %s", str(exc))
        return False


def alert_signal_fired(ticker: str, signal: str, amount: float) -> bool:
    message = (
        f"🤖 <b>Signal fired</b>\n"
        f"Ticker: {ticker}\n"
        f"Signal: {signal}\n"
        f"Amount: £{amount:.2f}"
    )
    return send_alert(message)


def alert_kill_switch(loss_pct: float) -> bool:
    message = (
        f"🛑 <b>Kill switch activated</b>\n"
        f"Daily loss limit breached\n"
        f"Loss: {loss_pct:.1%}"
    )
    return send_alert(message)


def alert_cycle_summary(status: str, orders_executed: int) -> bool:
    message = (
        f"📊 <b>Cycle complete</b>\n"
        f"Status: {status}\n"
        f"Orders executed: {orders_executed}"
    )
    return send_alert(message)
