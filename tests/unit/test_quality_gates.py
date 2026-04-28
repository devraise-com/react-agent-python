"""Unit tests for quality gate evaluation."""

from pathlib import Path

from src.agent.quality_gates import (
    GateThresholds,
    evaluate_quality_gates,
    load_task_completed_events,
)


def test_load_task_completed_events(tmp_path: Path) -> None:
    path = tmp_path / "audit.jsonl"
    path.write_text(
        "\n".join(
            [
                '{"event_type":"task_received","payload":{}}',
                '{"event_type":"task_completed","payload":{"outcome":"success"}}',
            ]
        ),
        encoding="utf-8",
    )
    events = load_task_completed_events(path)
    assert len(events) == 1
    assert events[0]["event_type"] == "task_completed"


def test_evaluate_quality_gates_passes() -> None:
    events = [
        {
            "event_type": "task_completed",
            "payload": {
                "outcome": "success",
                "hallucination_suspected": False,
                "usage": {"estimated_cost_usd": 0.01},
                "guardrails": {"tool_misuse_rate": 0.0, "loop_detected_rate": 0.0},
            },
        }
        for _ in range(10)
    ]
    result = evaluate_quality_gates(events)
    assert result.passed is True
    assert result.breaches == []


def test_evaluate_quality_gates_detects_breaches() -> None:
    events = [
        {
            "event_type": "task_completed",
            "payload": {
                "outcome": "failure",
                "hallucination_suspected": True,
                "usage": {"estimated_cost_usd": 0.5},
                "guardrails": {"tool_misuse_rate": 0.4, "loop_detected_rate": 0.3},
            },
        }
        for _ in range(5)
    ]
    result = evaluate_quality_gates(
        events,
        thresholds=GateThresholds(
            min_success_rate=0.9,
            max_tool_misuse_rate=0.05,
            max_loop_detected_rate=0.05,
            max_hallucination_rate=0.05,
            max_avg_cost_per_task_usd=0.05,
        ),
    )
    assert result.passed is False
    assert result.breaches
