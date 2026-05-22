from config.logger import get_logger
from config.settings import MAX_CONCURRENT_POSITIONS, MAX_RISK_PER_TRADE

TRADE_AMOUNT_LOG_FORMAT = "TRADE AMOUNT | signal=%s | capital=%.2f | amount=£%.2f"


def calculate_trade_amount(signal: str, capital: float) -> float:
    logger = get_logger(__name__)

    if signal == "HOLD":
        amount = 0.0
        logger.info(
            TRADE_AMOUNT_LOG_FORMAT,
            signal,
            capital,
            amount,
        )
        return amount

    if capital <= 0:
        logger.warning("Invalid capital for trade amount calculation")
        amount = 0.0
        logger.info(
            TRADE_AMOUNT_LOG_FORMAT,
            signal,
            capital,
            amount,
        )
        return amount

    amount = round(capital * MAX_RISK_PER_TRADE, 2)

    if amount < 1.0:
        logger.warning("Risk budget is too small to trade")
        amount = 0.0

    logger.info(
        TRADE_AMOUNT_LOG_FORMAT,
        signal,
        capital,
        amount,
    )
    return amount


def maybe_log_position_utilization(current_positions_count: int) -> None:
    logger = get_logger(__name__)
    threshold = max(1, int(MAX_CONCURRENT_POSITIONS * 0.8))
    if current_positions_count >= threshold:
        logger.warning(
            "POSITION UTILIZATION | current=%d | max=%d",
            current_positions_count,
            MAX_CONCURRENT_POSITIONS,
        )
