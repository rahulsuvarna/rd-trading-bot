from __future__ import annotations

import math
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.backtest import run_backtest


def _is_finite_or_inf(value: float) -> bool:
    return math.isfinite(value) or math.isinf(value)


def main() -> int:
    checks: list[tuple[str, bool, str]] = []

    last_error = None
    result = None
    for interval in ("5m", "15m", "30m", "60m"):
        try:
            result = run_backtest(symbol="SPY", period="3mo", interval=interval, initial_capital=1000.0)
            break
        except Exception as exc:
            last_error = exc

    if result is None:
        print("Verification failed: backtest execution error")
        print(f"Error: {last_error}")
        return 1

    metrics = result["metrics"]

    total_return = float(metrics.get("total_return_pct", float("nan")))
    sharpe = float(metrics.get("sharpe_ratio", float("nan")))
    max_dd = float(metrics.get("max_drawdown_pct", float("nan")))
    win_rate = float(metrics.get("win_rate_pct", float("nan")))
    trade_count = int(metrics.get("number_of_trades", 0))
    profit_factor = float(metrics.get("profit_factor", float("nan")))

    checks.append((
        "All required metrics present",
        all(k in metrics for k in [
            "total_return_pct",
            "sharpe_ratio",
            "max_drawdown_pct",
            "win_rate_pct",
            "profit_factor",
            "number_of_trades",
        ]),
        "Expected metrics keys exist",
    ))

    checks.append((
        "Metric values are finite/valid",
        all(
            _is_finite_or_inf(v)
            for v in [total_return, sharpe, max_dd, win_rate, profit_factor]
        ),
        "All numeric metrics are usable",
    ))

    checks.append((
        "Win rate between 0 and 100",
        0.0 <= win_rate <= 100.0,
        f"win_rate={win_rate:.2f}",
    ))

    checks.append((
        "Max drawdown is non-negative",
        max_dd >= 0.0,
        f"max_drawdown={max_dd:.2f}",
    ))

    checks.append((
        "Number of trades > 0",
        trade_count > 0,
        f"trades={trade_count}",
    ))

    passed = sum(1 for _, ok, _ in checks if ok)
    total = len(checks)

    print("Backtest Verification Report")
    print("=" * 40)
    for name, ok, detail in checks:
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] {name} | {detail}")

    print("-" * 40)
    print(f"Checks passed: {passed}/{total}")
    print("Metrics")
    print(f"  Interval Used: {result['interval']}")
    print(f"  Total Return %: {total_return:.2f}")
    print(f"  Sharpe Ratio: {sharpe:.4f}")
    print(f"  Max Drawdown %: {max_dd:.2f}")
    print(f"  Win Rate %: {win_rate:.2f}")
    print(f"  Profit Factor: {'inf' if math.isinf(profit_factor) else f'{profit_factor:.4f}'}")
    print(f"  Number of Trades: {trade_count}")

    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
