from config.logger import get_logger
from config.settings import MAX_CONCURRENT_POSITIONS
from risk.daily_loss_tracker import is_trading_allowed
from risk.position_sizer import calculate_trade_amount

RISK_GATE_LOG_FORMAT = "RISK GATE | signal=%s | approved=%s | amount=£%.2f | reason=%s"


def evaluate(signal: str, capital: float, current_positions_count: int = 0) -> dict:
    logger = get_logger(__name__)

    if not is_trading_allowed():
        decision = {
            "approved": False,
            "signal": signal,
            "trade_amount": 0.0,
            "reason": "kill_switch_active",
        }
        logger.info(
            RISK_GATE_LOG_FORMAT,
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
            RISK_GATE_LOG_FORMAT,
            decision["signal"],
            decision["approved"],
            decision["trade_amount"],
            decision["reason"],
        )
        return decision

    if signal == "BUY" and current_positions_count >= MAX_CONCURRENT_POSITIONS:
        decision = {
            "approved": False,
            "signal": signal,
            "trade_amount": 0.0,
            "reason": "max_concurrent_positions_reached",
        }
        logger.info(
            RISK_GATE_LOG_FORMAT,
            decision["signal"],
            decision["approved"],
            decision["trade_amount"],
            decision["reason"],
        )
        return decision

    amount = calculate_trade_amount(signal, capital)
    if amount <= 0.0:
        decision = {
            "approved": False,
            "signal": signal,
            "trade_amount": 0.0,
            "reason": "trade_amount_too_small",
        }
        logger.info(
            RISK_GATE_LOG_FORMAT,
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
        RISK_GATE_LOG_FORMAT,
        decision["signal"],
        decision["approved"],
        decision["trade_amount"],
        decision["reason"],
    )
    return decision
