from config.logger import get_logger
from risk.daily_loss_tracker import is_trading_allowed
from risk.position_sizer import calculate_trade_amount


def evaluate(signal: str, capital: float) -> dict:
    logger = get_logger(__name__)

    if not is_trading_allowed():
        decision = {
            "approved": False,
            "signal": signal,
            "trade_amount": 0.0,
            "reason": "kill_switch_active",
        }
        logger.info(
            "RISK GATE | signal=%s | approved=%s | amount=£%.2f | reason=%s",
            decision["signal"],
            decision["approved"],
            decision["trade_amount"],
            decision["reason"],
        )
        return decision

    if signal == "HOLD":
        decision = {
            "approved": False,
            "signal": "HOLD",
            "trade_amount": 0.0,
            "reason": "signal_is_hold",
        }
        logger.info(
            "RISK GATE | signal=%s | approved=%s | amount=£%.2f | reason=%s",
            decision["signal"],
            decision["approved"],
            decision["trade_amount"],
            decision["reason"],
        )
        return decision

    amount = calculate_trade_amount(signal, capital)
    if amount == 0.0:
        decision = {
            "approved": False,
            "signal": signal,
            "trade_amount": 0.0,
            "reason": "trade_amount_too_small",
        }
        logger.info(
            "RISK GATE | signal=%s | approved=%s | amount=£%.2f | reason=%s",
            decision["signal"],
            decision["approved"],
            decision["trade_amount"],
            decision["reason"],
        )
        return decision

    decision = {
        "approved": True,
        "signal": signal,
        "trade_amount": amount,
        "reason": "approved",
    }
    logger.info(
        "RISK GATE | signal=%s | approved=%s | amount=£%.2f | reason=%s",
        decision["signal"],
        decision["approved"],
        decision["trade_amount"],
        decision["reason"],
    )
    return decision
