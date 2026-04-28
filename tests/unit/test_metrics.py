"""Unit tests for detection metrics."""

from pathlib import Path

from src.agent.metrics import (
    get_avg_tokens_per_task,
    get_error_rate,
    get_p95_latency,
    get_steps_per_task,
    get_success_rate,
    get_tool_error_rate,
    load_task_completed_events,
)


def _events() -> list[dict]:
    return [
        {
            "event_type": "task_completed",
            "payload": {
                "outcome": "success",
                "duration_ms": 100,
                "llm_turns": 2,
                "tool_calls": 3,
                "tool_errors": 0,
                "usage": {"input_tokens": 100, "output_tokens": 50},
            },
        },
        {
            "event_type": "task_completed",
            "payload": {
                "outcome": "failure",
                "duration_ms": 200,
                "llm_turns": 4,
                "tool_calls": 2,
                "tool_errors": 1,
                "usage": {"input_tokens": 120, "output_tokens": 80},
            },
        },
        {
            "event_type": "task_completed",
            "payload": {
                "outcome": "clarification",
                "duration_ms": 300,
                "llm_turns": 1,
                "tool_calls": 0,
                "tool_errors": 0,
                "usage": {"input_tokens": 30, "output_tokens": 10},
            },
        },
    ]


def test_load_task_completed_events(tmp_path: Path) -> None:
    path = tmp_path / "audit.jsonl"
    path.write_text(
        "\n".join(
            [
                '{"event_type":"task_received","payload":{}}',
                '{"event_type":"task_completed","payload":{"outcome":"success"}}',
                '{"event_type":"task_completed","payload":{"outcome":"failure"}}',
            ]
        ),
        encoding="utf-8",
    )
    events = load_task_completed_events(path)
    assert len(events) == 2


def test_get_success_rate() -> None:
    assert get_success_rate(_events()) == (1 / 3)


def test_get_error_rate() -> None:
    assert get_error_rate(_events()) == (1 / 3)


def test_get_p95_latency() -> None:
    assert get_p95_latency(_events()) == 300.0


def test_get_avg_tokens_per_task() -> None:
    # (150 + 200 + 40) / 3
    assert get_avg_tokens_per_task(_events()) == 130.0


def test_get_steps_per_task() -> None:
    # (2 + 4 + 1) / 3
    assert get_steps_per_task(_events()) == (7 / 3)


def test_get_tool_error_rate() -> None:
    # total tool errors 1 / total tool calls 5
    assert get_tool_error_rate(_events()) == 0.2


def test_metric_functions_return_zero_on_empty() -> None:
    empty: list[dict] = []
    assert get_success_rate(empty) == 0.0
    assert get_error_rate(empty) == 0.0
    assert get_p95_latency(empty) == 0.0
    assert get_avg_tokens_per_task(empty) == 0.0
    assert get_steps_per_task(empty) == 0.0
    assert get_tool_error_rate(empty) == 0.0
