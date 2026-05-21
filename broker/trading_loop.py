"""Main trading cycle orchestrator."""

from typing import Any, Dict, Optional

from broker.order_executor import OrderExecutor
from config.logger import get_logger
from config.watchlist import WATCHLIST
from data.pipeline import run_pipeline
from monitoring.journal import record_cycle
from risk.daily_loss_tracker import (
    initialise,
    is_trading_allowed,
    record_trade_result,
    reset as reset_daily_tracker,
)
from risk.risk_gate import evaluate as risk_evaluate
from strategies.signal_runner import run_signals

logger = get_logger(__name__)


class Journal:
    """Minimal journal adapter for cycle persistence."""

    def write_cycle(self, cycle_result: Dict[str, Any]) -> None:
        record_cycle(cycle_result)


class TradingLoop:
    """Orchestrates one complete trading cycle."""

    def __init__(
        self,
        mode: str = "paper",
        starting_paper_cash: float = 1000.0,
        live_client: Optional[Any] = None,
        min_cash_threshold: float = 10.0,
    ):
        """
        Initialize trading loop.

        Args:
            mode: "paper" or "live"
            starting_paper_cash: Initial cash for paper mode
            live_client: Trading 212 client (only used in live mode)
            min_cash_threshold: Minimum cash required to trade
        """
        self.mode = mode
        self.starting_cash = starting_paper_cash
        self.executor = OrderExecutor(
            mode=mode,
            starting_paper_cash=starting_paper_cash,
            live_client=live_client,
        )
        self.live_client = live_client
        self.min_cash_threshold = min_cash_threshold
        self.journal = Journal()

        # Initialise daily loss tracker with starting cash
        initialise(starting_paper_cash)

    def get_available_cash(self) -> float:
        """Get available cash from executor."""
        return self.executor.get_available_cash()

    def get_positions(self) -> Dict[str, float]:
        """Get current positions from executor."""
        return self.executor.get_positions()

    def run_cycle(self) -> Dict[str, Any]:
        """
        Execute one trading cycle.

        Returns:
            Dict with cycle results: status, free_cash, reason, signals, orders
        """
        logger.info("Starting trading cycle")

        # 1. Check kill switch via daily loss tracker
        if not is_trading_allowed():
            logger.warning("Kill switch active - trading halted")
            return {
                "status": "aborted",
                "free_cash": self.get_available_cash(),
                "reason": "kill_switch_active",
                "signals": {},
                "orders": [],
            }

        # 2. Check cash availability
        free_cash = self.get_available_cash()
        logger.info("Available cash: £%.2f", free_cash)

        if free_cash < self.min_cash_threshold:
            logger.warning("Cash below threshold (£%.2f)", self.min_cash_threshold)
            return {
                "status": "aborted",
                "free_cash": free_cash,
                "reason": f"Cash below threshold: {free_cash}",
                "signals": {},
                "orders": [],
            }

        # 3. Run data pipeline for watchlist
        try:
            pipeline_data = run_pipeline()
            pipeline_data = {
                ticker: df
                for ticker, df in pipeline_data.items()
                if ticker in WATCHLIST
            }

            if not pipeline_data:
                logger.warning("No pipeline data returned")
                return {
                    "status": "aborted",
                    "free_cash": free_cash,
                    "reason": "No pipeline data",
                    "signals": {},
                    "orders": [],
                }
        except Exception as exc:
            logger.exception("Pipeline failed: %s", exc)
            return {
                "status": "aborted",
                "free_cash": free_cash,
                "reason": f"Pipeline error: {exc}",
                "signals": {},
                "orders": [],
            }

        # 4. Generate signals
        try:
            signals = run_signals(pipeline_data)
            logger.info("Generated signals: %s", signals)
        except Exception as exc:
            logger.exception("Signal generation failed: %s", exc)
            return {
                "status": "aborted",
                "free_cash": free_cash,
                "reason": f"Signal error: {exc}",
                "signals": {},
                "orders": [],
            }

        # 5. Process each signal through risk gate and execution
        orders = []
        approved_count = 0
        # enriched_signals keeps the original signal strings for HOLD tickers and
        # replaces BUY/SELL entries with a full dict after execution so the journal
        # has enough data to reconstruct trades even without the orders column.
        enriched_signals: Dict[str, Any] = dict(signals)

        for ticker, signal_data in signals.items():
            signal = "HOLD"
            price = 0.0

            if isinstance(signal_data, dict):
                signal = str(signal_data.get("signal", "HOLD"))
                price = float(signal_data.get("price", 0.0))
            else:
                signal = str(signal_data)

            if price <= 0 and ticker in pipeline_data:
                try:
                    price = float(pipeline_data[ticker].iloc[-1]["close"])
                except Exception:
                    price = 0.0

            if signal == "HOLD":
                continue

            # Run risk gate (only takes signal and capital)
            risk_decision = risk_evaluate(signal=signal, capital=free_cash)

            if not risk_decision["approved"]:
                logger.info("%s: Risk gate blocked - %s", ticker, risk_decision["reason"])
                continue

            approved_count += 1
            trade_amount = float(risk_decision["trade_amount"])

            # Execute order
            if signal == "BUY":
                order_result = self.executor.execute_order(
                    ticker, "BUY", trade_amount, price
                )
            else:  # SELL
                # For sell, we need current shares held
                current_position = self.get_positions().get(ticker, 0.0)
                if current_position <= 0:
                    logger.warning("%s: Cannot sell - no position held", ticker)
                    continue
                order_result = self.executor.execute_order(
                    ticker, "SELL", current_position, price
                )

            orders.append(order_result)

            # Enrich the signal entry with execution details for the journal.
            enriched_signals[ticker] = {
                "signal": signal,
                "price": price,
                "shares": order_result.get("shares"),
                "cost": order_result.get("cost"),
                "proceeds": order_result.get("proceeds"),
                "executed": order_result.get("executed", False),
            }

            if order_result["executed"]:
                logger.info("%s: Executed %s - %s", ticker, signal, order_result)

                # Calculate P&L for the trade and record in daily loss tracker.
                if (
                    signal == "SELL"
                    and "proceeds" in order_result
                    and "cost" in order_result
                ):
                    pnl = order_result["proceeds"] - order_result.get(
                        "cost_basis", trade_amount
                    )
                    record_trade_result(pnl)
            else:
                logger.warning(
                    "%s: Execution failed - %s",
                    ticker,
                    order_result.get("reason", "Unknown"),
                )

        # 6. Persist to journal
        cycle_result = {
            "status": "completed",
            "free_cash": self.get_available_cash(),
            "reason": None,
            "signals": enriched_signals,
            "orders": orders,
            "orders_executed": len([o for o in orders if o.get("executed")]),
            "orders_approved": approved_count,
        }

        self.journal.write_cycle(cycle_result)

        logger.info(
            "Cycle complete: %d approved, %d executed",
            approved_count,
            cycle_result["orders_executed"],
        )

        return cycle_result

    def reset_daily(self, starting_cash: float = None) -> None:
        """Reset daily loss tracker (call at market open)."""
        cash = starting_cash if starting_cash is not None else self.starting_cash
        reset_daily_tracker(cash)
        logger.info("Daily loss tracker reset with capital £%.2f", cash)

    def reset_paper_account(self, starting_cash: float = 1000.0) -> None:
        """Reset paper account (paper mode only)."""
        if self.mode == "paper":
            self.starting_cash = starting_cash
            self.executor.reset_paper_account(starting_cash)
            reset_daily_tracker(starting_cash)
            logger.info("Paper account reset to £%.2f", starting_cash)


class _LiveClientAdapter:
    """Adapter to keep compatibility with existing T212 client shape."""

    def __init__(self, client: Any):
        self.client = client

    def get_cash(self) -> float:
        if hasattr(self.client, "get_cash"):
            return float(self.client.get_cash())
        if hasattr(self.client, "get_account_cash"):
            payload = self.client.get_account_cash()
            if payload is None:
                return 0.0
            return float(payload.get("free", 0.0))
        raise RuntimeError("Live client not provided for live mode")

    def get_positions(self) -> Dict[str, float]:
        if hasattr(self.client, "get_positions"):
            positions = self.client.get_positions()
            return positions if isinstance(positions, dict) else {}
        return {}


_LOOPS: Dict[int, TradingLoop] = {}


def run_trading_cycle(client: Any) -> Dict[str, Any]:
    """Backward-compatible helper used by existing scheduler/main wiring."""
    key = id(client)
    if key not in _LOOPS:
        _LOOPS[key] = TradingLoop(
            mode="live",
            live_client=_LiveClientAdapter(client),
        )
    return _LOOPS[key].run_cycle()
