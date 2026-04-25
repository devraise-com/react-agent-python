"""Unit tests for the ReAct agent loop."""

from typing import Any

import pytest

from src.agent.llm_client import LLMError, LLMResponse, ToolCall
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
