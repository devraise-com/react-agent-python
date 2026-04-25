"""ReAct agent loop: Reason → Act → Observe → repeat."""

import json
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any, Literal

from src.agent.config import Settings
from src.agent.llm_client import LLMClient, LLMError, LLMResponse, ToolCall
from src.tools.base import ToolError
import structlog

from src.tools.registry import ToolRegistry

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT: dict[str, Any] = {
    "role": "system",
    "content": (
        "You are a workplace automation assistant. "
        "You help users perform actions across Slack, Google Calendar, Jira, and Email "
        "by calling the available tools.\n\n"
        "Rules:\n"
        "1. If the user's request is ambiguous or missing required details "
        "(e.g. 'send an update' with no channel, content, or recipient specified), "
        "ask ONE concise clarifying question. "
        "Do NOT call any tool until you have enough information.\n"
        "2. Only call a tool when all required parameters are known. "
        "If a tool returns an error, explain what went wrong and suggest what the user can do next.\n"
        "3. After completing all actions, present a brief summary of what was done "
        "(which tools were called and what the outcomes were).\n"
        "4. Never fabricate tool results. If a tool call fails, report the failure honestly."
    ),
}

# ---------------------------------------------------------------------------
# Step events
# ---------------------------------------------------------------------------

EventType = Literal[
    "reasoning", "tool_call", "tool_result", "tool_error", "error", "final_answer"
]


@dataclass
class StepEvent:
    type: EventType
    content: str | None = None
    name: str | None = None  # tool name (tool_call / tool_result / tool_error)
    args: dict[str, Any] = field(default_factory=dict)
    result: Any = None
    error: str | None = None


# ---------------------------------------------------------------------------
# Message helpers
# ---------------------------------------------------------------------------


def _assistant_msg(response: LLMResponse) -> dict[str, Any]:
    """Build the assistant message (content + all tool_calls) to append to history."""
    msg: dict[str, Any] = {"role": "assistant", "content": response.content}
    if response.tool_calls:
        msg["tool_calls"] = [
            {
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.name,
                    "arguments": json.dumps(tc.args),
                },
            }
            for tc in response.tool_calls
        ]
    return msg


def _tool_result_msg(tc: ToolCall, result: Any) -> dict[str, Any]:
    content = json.dumps(result) if not isinstance(result, str) else result
    return {"role": "tool", "tool_call_id": tc.id, "content": content}


def _tool_error_msg(tc: ToolCall, error: str) -> dict[str, Any]:
    return {"role": "tool", "tool_call_id": tc.id, "content": f"Error: {error}"}


# ---------------------------------------------------------------------------
# Agent loop
# ---------------------------------------------------------------------------


class AgentLoop:
    def __init__(
        self, llm: LLMClient, registry: ToolRegistry, settings: Settings
    ) -> None:
        self._llm = llm
        self._registry = registry
        self._max_steps = settings.max_agent_steps

    def run(self, user_message: str) -> Iterator[StepEvent]:
        """Run the ReAct loop; yields StepEvents including the final answer."""
        messages: list[dict[str, Any]] = [
            SYSTEM_PROMPT,
            {"role": "user", "content": user_message},
        ]
        seen_calls: set[tuple[str, str]] = set()

        for step in range(self._max_steps):
            logger.debug("agent_step", step=step, message_count=len(messages))

            # -- LLM call (retries handled inside OpenAIClient) ----------
            try:
                response = self._llm.chat(messages, self._registry.schemas())
            except LLMError as exc:
                logger.error("llm_error", error=str(exc))
                yield StepEvent(type="error", error=str(exc))
                yield StepEvent(
                    type="final_answer",
                    content=f"LLM unavailable: {exc}",
                )
                return

            # -- Reasoning text ------------------------------------------
            if response.content:
                logger.debug("reasoning", content=response.content[:120])
                yield StepEvent(type="reasoning", content=response.content)

            # -- No tool calls → final answer ----------------------------
            if not response.tool_calls:
                yield StepEvent(
                    type="final_answer", content=response.content or "Done."
                )
                return

            # -- Append full assistant message ONCE ----------------------
            messages.append(_assistant_msg(response))

            # -- Execute each tool call ----------------------------------
            for tc in response.tool_calls:
                # Guard: same tool + same args repeated → loop detected
                key = (tc.name, json.dumps(tc.args, sort_keys=True))
                if key in seen_calls:
                    logger.warning("loop_detected", tool=tc.name, args=tc.args)
                    yield StepEvent(
                        type="final_answer",
                        content="Loop detected: model repeated the same tool call.",
                    )
                    return
                seen_calls.add(key)

                yield StepEvent(type="tool_call", name=tc.name, args=tc.args)
                logger.info("tool_call", tool=tc.name, args=tc.args)

                try:
                    result = self._registry.dispatch(tc.name, tc.args)
                    logger.info("tool_result", tool=tc.name, result=result)
                    yield StepEvent(type="tool_result", name=tc.name, result=result)
                    messages.append(_tool_result_msg(tc, result))
                except ToolError as exc:
                    logger.warning("tool_error", tool=tc.name, error=str(exc))
                    yield StepEvent(type="tool_error", name=tc.name, error=str(exc))
                    # Send error back to the LLM so it can recover
                    messages.append(_tool_error_msg(tc, str(exc)))

        # Max steps exhausted
        yield StepEvent(type="final_answer", content="Max steps reached.")
