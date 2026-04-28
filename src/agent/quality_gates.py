"""Evaluate production quality gates from append-only audit logs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.agent.metrics import load_task_completed_events  # re-exported for callers

__all__ = [
    "GateThresholds",
    "GateResult",
    "evaluate_quality_gates",
    "load_task_completed_events",
]


@dataclass(frozen=True)
class GateThresholds:
    min_success_rate: float = 0.97
    max_tool_misuse_rate: float = 0.03
    max_loop_detected_rate: float = 0.02
    max_hallucination_rate: float = 0.02
    max_avg_cost_per_task_usd: float = 0.05


@dataclass(frozen=True)
class GateResult:
    passed: bool
    metrics: dict[str, float]
    breaches: list[str]


def evaluate_quality_gates(
    events: list[dict[str, Any]], thresholds: GateThresholds | None = None
) -> GateResult:
    t = thresholds or GateThresholds()
    if not events:
        return GateResult(
            passed=False,
            metrics={},
            breaches=["no task_completed events found"],
        )

    total = len(events)
    success = 0
    hallucinations = 0
    total_cost = 0.0
    avg_tool_misuse_rate = 0.0
    avg_loop_detected_rate = 0.0

    for event in events:
        payload = event.get("payload", {})
        if payload.get("outcome") == "success":
            success += 1
        if bool(payload.get("hallucination_suspected")):
            hallucinations += 1
        usage = payload.get("usage", {})
        total_cost += float(usage.get("estimated_cost_usd", 0.0) or 0.0)
        guardrails = payload.get("guardrails", {})
        avg_tool_misuse_rate += float(guardrails.get("tool_misuse_rate", 0.0) or 0.0)
        avg_loop_detected_rate += float(
            guardrails.get("loop_detected_rate", 0.0) or 0.0
        )

    metrics = {
        "task_count": float(total),
        "success_rate": success / total,
        "hallucination_rate": hallucinations / total,
        "avg_cost_per_task_usd": total_cost / total,
        "avg_tool_misuse_rate": avg_tool_misuse_rate / total,
        "avg_loop_detected_rate": avg_loop_detected_rate / total,
    }

    breaches: list[str] = []
    if metrics["success_rate"] < t.min_success_rate:
        breaches.append("success_rate below threshold")
    if metrics["hallucination_rate"] > t.max_hallucination_rate:
        breaches.append("hallucination_rate above threshold")
    if metrics["avg_tool_misuse_rate"] > t.max_tool_misuse_rate:
        breaches.append("tool_misuse_rate above threshold")
    if metrics["avg_loop_detected_rate"] > t.max_loop_detected_rate:
        breaches.append("loop_detected_rate above threshold")
    if metrics["avg_cost_per_task_usd"] > t.max_avg_cost_per_task_usd:
        breaches.append("avg_cost_per_task above threshold")

    return GateResult(passed=not breaches, metrics=metrics, breaches=breaches)

