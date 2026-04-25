"""Integration tests for scenarios A–D from the assignment spec."""

from typing import Any

import pytest

from src.agent.config import Settings
from src.agent.llm_client import LLMResponse, ToolCall
from src.agent.loop import AgentLoop, StepEvent
from src.tools.registry import ToolRegistry
from tests.conftest import ScriptedLLMClient


def _events(loop: AgentLoop, msg: str) -> list[StepEvent]:
    return list(loop.run(msg))


def _tool_calls(events: list[StepEvent]) -> list[StepEvent]:
    return [e for e in events if e.type == "tool_call"]


def _final_answer(events: list[StepEvent]) -> str:
    answers = [e for e in events if e.type == "final_answer"]
    assert answers, "No final_answer emitted"
    return answers[-1].content or ""


# ---------------------------------------------------------------------------
# Scenario A — Simple action: send Slack message
# ---------------------------------------------------------------------------


def test_scenario_a_slack_send_message(
    tmp_settings: Settings, full_registry: ToolRegistry
) -> None:
    """Agent identifies slack_send_message, calls it, confirms to user."""
    tc = ToolCall(
        id="tc1",
        name="slack_send_message",
        args={"channel": "#engineering", "text": "Deployment of v2.4.1 completed successfully."},
    )
    llm = ScriptedLLMClient(
        [
            LLMResponse(content=None, tool_calls=[tc]),
            LLMResponse(
                content="Message sent to #engineering: 'Deployment of v2.4.1 completed successfully.'",
                tool_calls=[],
            ),
        ]
    )
    loop = AgentLoop(llm, full_registry, tmp_settings)
    events = _events(loop, "Send a message to #engineering: Deployment of v2.4.1 completed successfully.")

    calls = _tool_calls(events)
    assert len(calls) == 1
    assert calls[0].name == "slack_send_message"
    assert calls[0].args["channel"] == "#engineering"
    assert "v2.4.1" in calls[0].args["text"]

    assert _final_answer(events)  # non-empty confirmation
    assert not any(e.type == "tool_error" for e in events)


# ---------------------------------------------------------------------------
# Scenario B — Multi-step: Jira ticket + Slack notification
# ---------------------------------------------------------------------------


def test_scenario_b_jira_and_slack(
    tmp_settings: Settings, full_registry: ToolRegistry
) -> None:
    """Agent creates a Jira issue, assigns it, then notifies Slack."""
    create_tc = ToolCall(
        id="tc1",
        name="jira_create_issue",
        args={"summary": "Login bug", "description": "Users cannot log in", "priority": "High"},
    )
    assign_tc = ToolCall(
        id="tc2",
        name="jira_transition_issue",
        args={"key": "PRJ-2", "status": "In Progress", "assignee": "john.doe"},
    )
    notify_tc = ToolCall(
        id="tc3",
        name="slack_send_message",
        args={"channel": "#backend-team", "text": "Jira ticket PRJ-2 created for login bug."},
    )

    llm = ScriptedLLMClient(
        [
            LLMResponse(content=None, tool_calls=[create_tc]),
            LLMResponse(content=None, tool_calls=[assign_tc]),
            LLMResponse(content=None, tool_calls=[notify_tc]),
            LLMResponse(
                content="Done! Created PRJ-2, assigned to john.doe, notified #backend-team.",
                tool_calls=[],
            ),
        ]
    )
    loop = AgentLoop(llm, full_registry, tmp_settings)
    events = _events(
        loop,
        "Create a Jira ticket for the login bug, assign it to me, then notify #backend-team on Slack.",
    )

    names = [e.name for e in _tool_calls(events)]
    assert "jira_create_issue" in names
    assert "jira_transition_issue" in names
    assert "slack_send_message" in names
    assert not any(e.type == "tool_error" for e in events)
    assert _final_answer(events)


# ---------------------------------------------------------------------------
# Scenario C — Search + aggregation: calendar
# ---------------------------------------------------------------------------


def test_scenario_c_calendar_events_and_free_slot(
    tmp_settings: Settings, full_registry: ToolRegistry
) -> None:
    """Agent lists events then finds a free slot."""
    list_tc = ToolCall(
        id="tc1",
        name="calendar_list_events",
        args={"start": "2026-04-28T00:00:00", "end": "2026-04-29T00:00:00"},
    )
    slot_tc = ToolCall(
        id="tc2",
        name="calendar_find_free_slot",
        args={
            "duration_minutes": 120,
            "after": "2026-04-28T09:00:00",
            "before": "2026-04-28T18:00:00",
        },
    )

    llm = ScriptedLLMClient(
        [
            LLMResponse(content=None, tool_calls=[list_tc]),
            LLMResponse(content=None, tool_calls=[slot_tc]),
            LLMResponse(
                content="You have 2 events on Monday. First free 2-hour slot: 09:30–11:30.",
                tool_calls=[],
            ),
        ]
    )
    loop = AgentLoop(llm, full_registry, tmp_settings)
    events = _events(loop, "Show me all my calendar events this week and find a free 2-hour slot.")

    names = [e.name for e in _tool_calls(events)]
    assert "calendar_list_events" in names
    assert "calendar_find_free_slot" in names
    assert "2-hour" in _final_answer(events).lower() or "slot" in _final_answer(events).lower()


# ---------------------------------------------------------------------------
# Scenario D — Ambiguous prompt: agent asks for clarification
# ---------------------------------------------------------------------------


def test_scenario_d_ambiguous_prompt_no_tool_calls(
    tmp_settings: Settings, full_registry: ToolRegistry
) -> None:
    """Agent should ask for clarification, not call any tool."""
    llm = ScriptedLLMClient(
        [
            LLMResponse(
                content="Could you clarify? Where should I send the update (Slack channel, email?), and what should the message say?",
                tool_calls=[],
            )
        ]
    )
    loop = AgentLoop(llm, full_registry, tmp_settings)
    events = _events(loop, "Send an update.")

    assert not _tool_calls(events), "No tool should be called for an ambiguous prompt"
    answer = _final_answer(events)
    assert answer  # model returned a clarifying question
