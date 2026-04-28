#!/usr/bin/env python3
"""CI quality gate checker.

Reads an audit JSONL file produced by the agent, evaluates production quality
gates, prints a summary report, and exits with code 1 if any gate is breached.

Usage:
    python scripts/check_quality_gates.py runtime/audit_events.jsonl
    python scripts/check_quality_gates.py runtime/audit_events.jsonl \\
        --min-success-rate 0.95 --max-avg-cost-per-task-usd 0.10
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Make the project root importable when invoked directly.
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.agent.metrics import load_task_completed_events
from src.agent.quality_gates import GateThresholds, evaluate_quality_gates


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Evaluate production quality gates from an agent audit log."
    )
    p.add_argument("audit_log", type=Path, help="Path to audit JSONL file")
    p.add_argument(
        "--min-success-rate",
        type=float,
        default=GateThresholds.min_success_rate,
        metavar="RATE",
        help="Minimum success rate in [0, 1] (default: %(default)s)",
    )
    p.add_argument(
        "--max-tool-misuse-rate",
        type=float,
        default=GateThresholds.max_tool_misuse_rate,
        metavar="RATE",
        help="Maximum tool-misuse rate in [0, 1] (default: %(default)s)",
    )
    p.add_argument(
        "--max-loop-detected-rate",
        type=float,
        default=GateThresholds.max_loop_detected_rate,
        metavar="RATE",
        help="Maximum loop-detected rate in [0, 1] (default: %(default)s)",
    )
    p.add_argument(
        "--max-hallucination-rate",
        type=float,
        default=GateThresholds.max_hallucination_rate,
        metavar="RATE",
        help="Maximum hallucination-suspected rate in [0, 1] (default: %(default)s)",
    )
    p.add_argument(
        "--max-avg-cost-per-task-usd",
        type=float,
        default=GateThresholds.max_avg_cost_per_task_usd,
        metavar="USD",
        help="Maximum average cost per task in USD (default: %(default)s)",
    )
    return p.parse_args()


def main() -> None:
    args = _parse_args()

    events = load_task_completed_events(args.audit_log)
    print(f"Loaded {len(events)} task_completed events from {args.audit_log}")

    thresholds = GateThresholds(
        min_success_rate=args.min_success_rate,
        max_tool_misuse_rate=args.max_tool_misuse_rate,
        max_loop_detected_rate=args.max_loop_detected_rate,
        max_hallucination_rate=args.max_hallucination_rate,
        max_avg_cost_per_task_usd=args.max_avg_cost_per_task_usd,
    )

    result = evaluate_quality_gates(events, thresholds)

    col_w = 32
    print("\n--- Quality Gate Metrics ---")
    for key, value in result.metrics.items():
        label = key.replace("_", " ").title()
        print(f"  {label:<{col_w}} {value:.4f}")

    print("\n--- Thresholds ---")
    print(f"  {'Min success rate':<{col_w}} {thresholds.min_success_rate:.4f}")
    print(f"  {'Max tool misuse rate':<{col_w}} {thresholds.max_tool_misuse_rate:.4f}")
    print(f"  {'Max loop detected rate':<{col_w}} {thresholds.max_loop_detected_rate:.4f}")
    print(f"  {'Max hallucination rate':<{col_w}} {thresholds.max_hallucination_rate:.4f}")
    print(f"  {'Max avg cost per task (USD)':<{col_w}} {thresholds.max_avg_cost_per_task_usd:.4f}")

    if result.passed:
        print("\nAll quality gates PASSED.")
        sys.exit(0)
    else:
        print(f"\nQuality gates FAILED ({len(result.breaches)} breach(es)):")
        for breach in result.breaches:
            print(f"  - {breach}")
        sys.exit(1)


if __name__ == "__main__":
    main()
