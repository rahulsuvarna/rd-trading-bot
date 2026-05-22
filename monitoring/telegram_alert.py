"""Telegram alert sending module."""

from datetime import datetime

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


def _format_signal_line(ticker: str, signal_payload: object) -> str | None:
    if isinstance(signal_payload, str):
        if signal_payload.upper() == "HOLD":
            return None
        return f"{ticker} → {signal_payload.upper()} ❌"

    if not isinstance(signal_payload, dict):
        return None

    signal = str(signal_payload.get("signal", "")).upper() or "UNKNOWN"
    executed = bool(signal_payload.get("executed", False))

    if executed:
        amount_value = signal_payload.get("cost")
        if amount_value is None:
            amount_value = signal_payload.get("proceeds", 0.0)
        amount = float(amount_value or 0.0)
        return f"{ticker} → {signal} £{amount:.2f} ✅"

    reason = signal_payload.get("reason")
    if reason:
        return f"{ticker} → {signal} ❌ ({reason})"
    return f"{ticker} → {signal} ❌"


def alert_cycle_detail(cycle_result: dict) -> bool:
    timestamp = datetime.now().strftime("%H:%M")
    signals = cycle_result.get("signals", {})
    lines: list[str] = []

    if isinstance(signals, dict):
        for ticker, signal_payload in signals.items():
            line = _format_signal_line(ticker, signal_payload)
            if line:
                lines.append(line)

    if not lines:
        return send_alert("😴 All signals HOLD — no trades this cycle")

    free_cash = float(cycle_result.get("free_cash", 0.0) or 0.0)
    message = "\n".join(
        [
            f"📊 <b>Cycle complete</b> | {timestamp}",
            *lines,
            f"💰 Cash remaining: £{free_cash:.2f}",
        ]
    )
    return send_alert(message)
