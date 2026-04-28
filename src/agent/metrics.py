"""Detection metrics computed from task-completed audit events."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any


def load_task_completed_events(path: Path) -> list[dict[str, Any]]:
    """Load task-completed events from an audit JSONL file."""
    if not path.exists():
        return []

    events: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        raw = line.strip()
        if not raw:
            continue
        row = json.loads(raw)
        if row.get("event_type") == "task_completed":
            events.append(row)
    return events


def _payloads(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Extract the payload dict from each task_completed event."""
    return [event["payload"] for event in events if isinstance(event.get("payload"), dict)]


def get_success_rate(events: list[dict[str, Any]]) -> float:
    """Return success ratio in [0.0, 1.0]."""
    payloads = _payloads(events)
    if not payloads:
        return 0.0
    success = sum(1 for p in payloads if p.get("outcome") == "success")
    return success / len(payloads)


def get_error_rate(events: list[dict[str, Any]]) -> float:
    """Return failure ratio in [0.0, 1.0]."""
    payloads = _payloads(events)
    if not payloads:
        return 0.0
    failures = sum(1 for p in payloads if p.get("outcome") == "failure")
    return failures / len(payloads)


def get_p95_latency(events: list[dict[str, Any]]) -> float:
    """Return p95 task latency in milliseconds."""
    payloads = _payloads(events)
    latencies = [
        float(p["duration_ms"])
        for p in payloads
        if isinstance(p.get("duration_ms"), (int, float))
    ]
    if not latencies:
        return 0.0
    latencies.sort()
    rank = max(1, math.ceil(0.95 * len(latencies)))
    return latencies[rank - 1]


def get_avg_tokens_per_task(events: list[dict[str, Any]]) -> float:
    """Return average total tokens (input + output) per task."""
    payloads = _payloads(events)
    if not payloads:
        return 0.0

    totals: list[float] = []
    for p in payloads:
        usage = p.get("usage", {})
        if not isinstance(usage, dict):
            continue
        input_tokens = float(usage.get("input_tokens", 0) or 0)
        output_tokens = float(usage.get("output_tokens", 0) or 0)
        totals.append(input_tokens + output_tokens)
    if not totals:
        return 0.0
    return sum(totals) / len(totals)


def get_steps_per_task(events: list[dict[str, Any]]) -> float:
    """Return average number of LLM steps (turns) per task."""
    payloads = _payloads(events)
    steps = [
        float(p["llm_turns"])
        for p in payloads
        if isinstance(p.get("llm_turns"), (int, float))
    ]
    if not steps:
        return 0.0
    return sum(steps) / len(steps)


def get_tool_error_rate(events: list[dict[str, Any]]) -> float:
    """Return tool errors / tool calls ratio in [0.0, 1.0]."""
    payloads = _payloads(events)
    total_calls = 0.0
    total_errors = 0.0
    for p in payloads:
        calls = p.get("tool_calls")
        errors = p.get("tool_errors")
        if isinstance(calls, (int, float)):
            total_calls += float(calls)
        if isinstance(errors, (int, float)):
            total_errors += float(errors)
    if total_calls <= 0.0:
        return 0.0
    return total_errors / total_calls
