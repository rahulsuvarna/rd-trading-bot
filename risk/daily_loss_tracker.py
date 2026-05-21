from config.logger import get_logger
from config.settings import DAILY_LOSS_LIMIT

_state = {"starting_capital": 0.0, "current_capital": 0.0, "is_killed": False}


def initialise(starting_capital: float) -> None:
    logger = get_logger(__name__)
    _state["starting_capital"] = float(starting_capital)
    _state["current_capital"] = float(starting_capital)
    _state["is_killed"] = False
    logger.info("DAILY TRACKER | initialised | capital=£%.2f", starting_capital)


def record_trade_result(pnl: float) -> None:
    logger = get_logger(__name__)
    _state["current_capital"] = float(_state["current_capital"]) + float(pnl)
    _check_kill_switch()
    logger.info(
        "DAILY TRACKER | pnl=£%.2f | current=£%.2f",
        pnl,
        float(_state["current_capital"]),
    )


def _check_kill_switch() -> None:
    logger = get_logger(__name__)
    starting = float(_state["starting_capital"])
    current = float(_state["current_capital"])

    if starting <= 0:
        return

    loss = (current - starting) / starting
    if loss <= -DAILY_LOSS_LIMIT:
        _state["is_killed"] = True
        logger.warning(
            "KILL SWITCH ACTIVATED | daily loss limit breached | loss=%.1f%%",
            loss * 100,
        )


def is_trading_allowed() -> bool:
    logger = get_logger(__name__)
    if bool(_state["is_killed"]):
        logger.warning("TRADING HALTED | kill switch is active")
        return False
    return True


def get_summary() -> dict:
    starting = float(_state["starting_capital"])
    current = float(_state["current_capital"])
    pnl = current - starting
    loss_pct = 0.0
    if starting > 0:
        loss_pct = (current - starting) / starting

    return {
        "starting_capital": starting,
        "current_capital": current,
        "pnl": pnl,
        "loss_pct": loss_pct,
        "is_killed": bool(_state["is_killed"]),
    }


def reset(starting_capital: float) -> None:
    """Reset the daily loss tracker with new starting capital."""
    logger = get_logger(__name__)
    _state["starting_capital"] = float(starting_capital)
    _state["current_capital"] = float(starting_capital)
    _state["is_killed"] = False
    logger.info("DAILY TRACKER | reset | capital=£%.2f", starting_capital)
