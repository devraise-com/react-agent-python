"""Golden test suite for the ReAct agent loop.

Each case defines:
  - A scripted LLM sequence (deterministic, no real API call).
  - The expected tool-call sequence (ordered list of tool names).
  - The expected outcome class ("success" | "failure" | "clarification").
  - Hard budget limits: max_steps and max_cost_usd.

Golden cases cover the four mandatory scenario types from the production
readiness plan (doc 02):
  1. Happy-path workflow.
  2. Ambiguous request requiring clarification.
  3. Tool failure + recovery.
  4. Adversarial prompt targeting tool misuse (loop detection).

The runner reads the per-task audit JSONL written by the loop and asserts
machine-checkable expectations without relying on the real OpenAI API.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from src.agent.llm_client import LLMResponse, LLMUsage, ToolCall
from src.agent.loop import AgentLoop, StepEvent
from src.tools.registry import ToolRegistry
from tests.conftest import ScriptedLLMClient


# ---------------------------------------------------------------------------
# Golden case dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GoldenCase:
    name: str
    prompt: str
    llm_script: list[LLMResponse]
    expected_tool_sequence: list[str]
    expected_outcome: str  # "success" | "failure" | "clarification"
    max_steps: int
    max_cost_usd: float = 1.0


# ---------------------------------------------------------------------------
# Case definitions
# ---------------------------------------------------------------------------

GOLDEN_CASES: list[GoldenCase] = [
    # ------------------------------------------------------------------
    # 1. Happy path: single tool call, confirmed success
    # ------------------------------------------------------------------
    GoldenCase(
        name="happy_path_slack_send",
        prompt="Send a Slack message to #engineering: Deployment v2.5.0 done.",
        llm_script=[
            LLMResponse(
                content=None,
                tool_calls=[
                    ToolCall(
                        id="tc1",
                        name="slack_send_message",
                        args={
                            "channel": "#engineering",
                            "text": "Deployment v2.5.0 done.",
                        },
                    )
                ],
                usage=LLMUsage(input_tokens=300, output_tokens=50),
            ),
            LLMResponse(
                content="Message sent to #engineering.",
                tool_calls=[],
                usage=LLMUsage(input_tokens=350, output_tokens=30),
            ),
        ],
        expected_tool_sequence=["slack_send_message"],
        expected_outcome="success",
        max_steps=3,
        max_cost_usd=0.05,
    ),
    # ------------------------------------------------------------------
    # 2. Happy path: multi-step workflow (Jira + Slack)
    # ------------------------------------------------------------------
    GoldenCase(
        name="happy_path_jira_then_slack",
        prompt="Create a Jira bug 'Login broken' and notify #ops on Slack.",
        llm_script=[
            LLMResponse(
                content=None,
                tool_calls=[
                    ToolCall(
                        id="tc1",
                        name="jira_create_issue",
                        args={
                            "summary": "Login broken",
                            "description": "Users cannot log in.",
                            "priority": "High",
                        },
                    )
                ],
                usage=LLMUsage(input_tokens=400, output_tokens=80),
            ),
            LLMResponse(
                content=None,
                tool_calls=[
                    ToolCall(
                        id="tc2",
                        name="slack_send_message",
                        args={
                            "channel": "#ops",
                            "text": "Jira issue created for login bug.",
                        },
                    )
                ],
                usage=LLMUsage(input_tokens=500, output_tokens=60),
            ),
            LLMResponse(
                content="Done. Jira issue created and Slack notified.",
                tool_calls=[],
                usage=LLMUsage(input_tokens=600, output_tokens=40),
            ),
        ],
        expected_tool_sequence=["jira_create_issue", "slack_send_message"],
        expected_outcome="success",
        max_steps=5,
        max_cost_usd=0.05,
    ),
    # ------------------------------------------------------------------
    # 3. Clarification: ambiguous request
    # ------------------------------------------------------------------
    GoldenCase(
        name="clarification_ambiguous_request",
        prompt="Send an update.",
        llm_script=[
            LLMResponse(
                content="Could you clarify what update you'd like to send and where?",
                tool_calls=[],
                usage=LLMUsage(input_tokens=200, output_tokens=25),
            ),
        ],
        expected_tool_sequence=[],
        expected_outcome="clarification",
        max_steps=2,
        max_cost_usd=0.01,
    ),
    # ------------------------------------------------------------------
    # 4. Tool failure + recovery: unknown tool, then valid fallback
    # ------------------------------------------------------------------
    GoldenCase(
        name="tool_failure_recovery",
        prompt="Use the nonexistent_tool, then send a Slack message to #general.",
        llm_script=[
            LLMResponse(
                content=None,
                tool_calls=[
                    ToolCall(id="tc1", name="nonexistent_tool", args={"x": 1})
                ],
                usage=LLMUsage(input_tokens=300, output_tokens=40),
            ),
            LLMResponse(
                content=None,
                tool_calls=[
                    ToolCall(
                        id="tc2",
                        name="slack_send_message",
                        args={"channel": "#general", "text": "Fallback message."},
                    )
                ],
                usage=LLMUsage(input_tokens=400, output_tokens=50),
            ),
            LLMResponse(
                content="Done. Slack message sent after recovery.",
                tool_calls=[],
                usage=LLMUsage(input_tokens=500, output_tokens=30),
            ),
        ],
        expected_tool_sequence=["nonexistent_tool", "slack_send_message"],
        expected_outcome="success",
        max_steps=5,
        max_cost_usd=0.05,
    ),
    # ------------------------------------------------------------------
    # 5. Adversarial: loop detection (same tool + args repeated)
    # ------------------------------------------------------------------
    GoldenCase(
        name="adversarial_loop_detection",
        prompt="Keep listing Slack channels forever.",
        llm_script=[
            LLMResponse(
                content=None,
                tool_calls=[ToolCall(id="tc1", name="slack_list_channels", args={})],
                usage=LLMUsage(input_tokens=200, output_tokens=20),
            ),
            LLMResponse(
                content=None,
                tool_calls=[ToolCall(id="tc2", name="slack_list_channels", args={})],
                usage=LLMUsage(input_tokens=300, output_tokens=20),
            ),
        ],
        expected_tool_sequence=["slack_list_channels"],
        expected_outcome="failure",
        max_steps=5,
        max_cost_usd=0.05,
    ),
]


# ---------------------------------------------------------------------------
# Golden runner helper
# ---------------------------------------------------------------------------


def _run_golden_case(
    case: GoldenCase,
    settings: Any,
    registry: ToolRegistry,
) -> None:
    llm = ScriptedLLMClient(list(case.llm_script))
    loop = AgentLoop(llm, registry, settings)
    events: list[StepEvent] = list(loop.run(case.prompt))

    # --- Tool sequence ---------------------------------------------------
    actual_tools = [e.name for e in events if e.type == "tool_call"]
    assert actual_tools == case.expected_tool_sequence, (
        f"[{case.name}] Tool sequence mismatch.\n"
        f"  Expected: {case.expected_tool_sequence}\n"
        f"  Actual:   {actual_tools}"
    )

    # --- Outcome from audit log ------------------------------------------
    audit_path: Path = settings.runtime_dir / settings.audit_log_file
    raw_lines = audit_path.read_text(encoding="utf-8").strip().splitlines()
    audit_events = [json.loads(line) for line in raw_lines if line.strip()]
    completed = [e for e in audit_events if e.get("event_type") == "task_completed"]
    assert completed, f"[{case.name}] No task_completed event in audit log"
    actual_outcome = completed[-1]["payload"]["outcome"]
    assert actual_outcome == case.expected_outcome, (
        f"[{case.name}] Outcome mismatch: expected '{case.expected_outcome}', "
        f"got '{actual_outcome}'"
    )

    # --- Step budget -----------------------------------------------------
    llm_turns = completed[-1]["payload"]["llm_turns"]
    assert llm_turns <= case.max_steps, (
        f"[{case.name}] Exceeded max_steps: {llm_turns} > {case.max_steps}"
    )

    # --- Cost budget -----------------------------------------------------
    cost = completed[-1]["payload"]["usage"]["estimated_cost_usd"]
    assert cost <= case.max_cost_usd, (
        f"[{case.name}] Exceeded max_cost_usd: {cost:.6f} > {case.max_cost_usd}"
    )


# ---------------------------------------------------------------------------
# Parametrized golden test
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("case", GOLDEN_CASES, ids=[c.name for c in GOLDEN_CASES])
def test_golden_case(case: GoldenCase, tmp_settings: Any, full_registry: ToolRegistry) -> None:
    _run_golden_case(case, tmp_settings, full_registry)
