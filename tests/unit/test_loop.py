"""Unit tests for the ReAct agent loop."""

import json
from typing import Any

import pytest

from src.agent.llm_client import LLMError, LLMResponse, LLMUsage, ToolCall
from src.agent.loop import AgentLoop, StepEvent
from src.tools.registry import ToolRegistry
from tests.conftest import ScriptedLLMClient


def _collect(loop: AgentLoop, msg: str) -> list[StepEvent]:
    return list(loop.run(msg))


def _final(events: list[StepEvent]) -> StepEvent:
    answers = [e for e in events if e.type == "final_answer"]
    assert answers, "No final_answer event emitted"
    return answers[-1]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def empty_registry() -> ToolRegistry:
    return ToolRegistry()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_simple_text_answer(tmp_settings: Any, empty_registry: ToolRegistry) -> None:
    """Loop returns the LLM text directly when no tools are called."""
    llm = ScriptedLLMClient([LLMResponse(content="Hello!", tool_calls=[])])
    loop = AgentLoop(llm, empty_registry, tmp_settings)

    events = _collect(loop, "Hi")
    final = _final(events)
    assert final.content == "Hello!"


def test_none_content_falls_back_to_done(
    tmp_settings: Any, empty_registry: ToolRegistry
) -> None:
    llm = ScriptedLLMClient([LLMResponse(content=None, tool_calls=[])])
    loop = AgentLoop(llm, empty_registry, tmp_settings)

    final = _final(_collect(loop, "Hi"))
    assert final.content == "Done."


def test_reasoning_event_emitted(
    tmp_settings: Any, empty_registry: ToolRegistry
) -> None:
    llm = ScriptedLLMClient([LLMResponse(content="Thinking...", tool_calls=[])])
    loop = AgentLoop(llm, empty_registry, tmp_settings)

    events = _collect(loop, "hi")
    reasoning = [e for e in events if e.type == "reasoning"]
    assert reasoning and reasoning[0].content == "Thinking..."


def test_none_content_no_reasoning_event(
    tmp_settings: Any, empty_registry: ToolRegistry
) -> None:
    llm = ScriptedLLMClient([LLMResponse(content=None, tool_calls=[])])
    loop = AgentLoop(llm, empty_registry, tmp_settings)

    events = _collect(loop, "hi")
    assert not any(e.type == "reasoning" for e in events)


def test_single_tool_call_then_answer(
    tmp_settings: Any, full_registry: ToolRegistry
) -> None:
    tc = ToolCall(id="tc1", name="slack_list_channels", args={})
    llm = ScriptedLLMClient(
        [
            LLMResponse(content=None, tool_calls=[tc]),
            LLMResponse(content="Done listing channels.", tool_calls=[]),
        ]
    )
    loop = AgentLoop(llm, full_registry, tmp_settings)
    events = _collect(loop, "list slack channels")

    tool_call_events = [e for e in events if e.type == "tool_call"]
    tool_result_events = [e for e in events if e.type == "tool_result"]
    assert len(tool_call_events) == 1
    assert tool_call_events[0].name == "slack_list_channels"
    assert len(tool_result_events) == 1
    assert _final(events).content == "Done listing channels."


def test_tool_error_sent_back_to_llm(
    tmp_settings: Any, full_registry: ToolRegistry
) -> None:
    """ToolError should produce a tool_error event and allow the LLM to continue."""
    tc = ToolCall(id="tc1", name="slack_send_message", args={"channel": "#nonexistent", "text": "hi"})
    llm = ScriptedLLMClient(
        [
            LLMResponse(content=None, tool_calls=[tc]),
            LLMResponse(content="Channel not found, sorry.", tool_calls=[]),
        ]
    )
    loop = AgentLoop(llm, full_registry, tmp_settings)
    events = _collect(loop, "send hi to #nonexistent")

    error_events = [e for e in events if e.type == "tool_error"]
    assert error_events
    assert "not found" in (error_events[0].error or "").lower()
    assert _final(events).content == "Channel not found, sorry."


def test_loop_detection(tmp_settings: Any, full_registry: ToolRegistry) -> None:
    """Same tool + same args repeated twice → loop detected."""
    tc = ToolCall(id="tc1", name="slack_list_channels", args={})
    llm = ScriptedLLMClient(
        [
            LLMResponse(content=None, tool_calls=[tc]),
            LLMResponse(content=None, tool_calls=[tc]),  # repeat
        ]
    )
    loop = AgentLoop(llm, full_registry, tmp_settings)
    events = _collect(loop, "list channels")

    final = _final(events)
    assert "loop detected" in (final.content or "").lower()


def test_llm_error_yields_error_event(
    tmp_settings: Any, empty_registry: ToolRegistry
) -> None:
    class FailingLLM(ScriptedLLMClient):
        def chat(self, messages: Any, tools: Any) -> LLMResponse:
            raise LLMError("API down")

    loop = AgentLoop(FailingLLM([]), empty_registry, tmp_settings)
    events = _collect(loop, "hello")

    error_events = [e for e in events if e.type == "error"]
    assert error_events
    final = _final(events)
    assert "llm unavailable" in (final.content or "").lower()


def test_max_steps_reached(tmp_settings: Any, full_registry: ToolRegistry) -> None:
    """Loop exits gracefully after max_agent_steps."""
    # Use email_search with unique queries each step to avoid loop detection
    responses = [
        LLMResponse(
            content=None,
            tool_calls=[ToolCall(id=f"tc{i}", name="email_search", args={"query": f"q{i}"})],
        )
        for i in range(tmp_settings.max_agent_steps + 1)
    ]
    llm = ScriptedLLMClient(responses)
    loop = AgentLoop(llm, full_registry, tmp_settings)
    events = _collect(loop, "keep searching")

    final = _final(events)
    assert "max steps" in (final.content or "").lower()


def test_unknown_tool_produces_tool_error(
    tmp_settings: Any, empty_registry: ToolRegistry
) -> None:
    tc = ToolCall(id="tc1", name="nonexistent_tool", args={})
    llm = ScriptedLLMClient(
        [
            LLMResponse(content=None, tool_calls=[tc]),
            LLMResponse(content="I can't do that.", tool_calls=[]),
        ]
    )
    loop = AgentLoop(llm, empty_registry, tmp_settings)
    events = _collect(loop, "do something")

    error_events = [e for e in events if e.type == "tool_error"]
    assert error_events
    assert "nonexistent_tool" in (error_events[0].error or "")


def test_tool_error_is_sent_as_structured_json(
    tmp_settings: Any, empty_registry: ToolRegistry
) -> None:
    class CapturingLLM(ScriptedLLMClient):
        def __init__(self) -> None:
            self.last_messages: list[dict[str, Any]] = []
            super().__init__(
                [
                    LLMResponse(
                        content=None,
                        tool_calls=[ToolCall(id="tc1", name="missing_tool", args={})],
                    ),
                    LLMResponse(content="Recovered.", tool_calls=[]),
                ]
            )

        def chat(self, messages: Any, tools: Any) -> LLMResponse:
            self.last_messages = messages
            return super().chat(messages, tools)

    llm = CapturingLLM()
    loop = AgentLoop(llm, empty_registry, tmp_settings)
    events = _collect(loop, "do something")

    tool_messages = [m for m in llm.last_messages if m.get("role") == "tool"]
    assert tool_messages
    payload = json.loads(tool_messages[-1]["content"])
    assert payload["ok"] is False
    assert payload["error"]["code"] == "unknown_tool"
    assert "missing_tool" in payload["error"]["message"]
    assert _final(events).content == "Recovered."


def test_events_include_task_and_trace_ids(
    tmp_settings: Any, empty_registry: ToolRegistry
) -> None:
    llm = ScriptedLLMClient([LLMResponse(content="Hello!", tool_calls=[])])
    loop = AgentLoop(llm, empty_registry, tmp_settings)
    events = _collect(loop, "Hi")

    task_ids = {e.task_id for e in events}
    trace_ids = {e.trace_id for e in events}
    assert len(task_ids) == 1
    assert len(trace_ids) == 1
    assert None not in task_ids
    assert None not in trace_ids


def test_task_completed_audit_event_contains_usage_and_cost(
    tmp_settings: Any, empty_registry: ToolRegistry
) -> None:
    llm = ScriptedLLMClient(
        [
            LLMResponse(
                content="Done.",
                tool_calls=[],
                usage=LLMUsage(input_tokens=1200, output_tokens=400, cached_tokens=200),
            )
        ]
    )
    loop = AgentLoop(llm, empty_registry, tmp_settings)
    _collect(loop, "Hi")

    audit_path = tmp_settings.runtime_dir / tmp_settings.audit_log_file
    lines = audit_path.read_text(encoding="utf-8").strip().splitlines()
    events = [json.loads(line) for line in lines if line.strip()]
    completed = [e for e in events if e["event_type"] == "task_completed"]
    assert completed
    payload = completed[-1]["payload"]
    assert payload["usage"]["input_tokens"] == 1200
    assert payload["usage"]["output_tokens"] == 400
    assert payload["usage"]["cached_tokens"] == 200
    assert payload["usage"]["estimated_cost_usd"] > 0.0


def test_outcome_is_success_after_tool_error_recovery(
    tmp_settings: Any, full_registry: ToolRegistry
) -> None:
    """outcome must be 'success' when LLM recovers from a tool error."""
    bad_tc = ToolCall(id="tc1", name="missing_tool", args={})
    recovery = LLMResponse(content="All done.", tool_calls=[])
    llm = ScriptedLLMClient(
        [
            LLMResponse(content=None, tool_calls=[bad_tc]),
            recovery,
        ]
    )
    loop = AgentLoop(llm, full_registry, tmp_settings)
    _collect(loop, "Do something")

    audit_path = tmp_settings.runtime_dir / tmp_settings.audit_log_file
    lines = audit_path.read_text(encoding="utf-8").strip().splitlines()
    events = [json.loads(line) for line in lines if line.strip()]
    completed = [e for e in events if e["event_type"] == "task_completed"]
    assert completed
    assert completed[-1]["payload"]["outcome"] == "success"
