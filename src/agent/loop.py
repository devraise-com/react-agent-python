"""ReAct agent loop: Reason → Act → Observe → repeat."""

import hashlib
import json
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any, Literal

from src.agent.config import Settings
from src.agent.llm_client import LLMClient, LLMError, LLMResponse, ToolCall
from src.agent.telemetry import AuditLogger, CostEstimator, TaskContext, TaskMetrics
from src.agent.tracing import build_tracing_manager
from src.tools.base import ToolError
import structlog
from structlog import contextvars as log_contextvars

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
    task_id: str | None = None
    trace_id: str | None = None


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


def _tool_error_msg(tc: ToolCall, error: ToolError) -> dict[str, Any]:
    payload = {"ok": False, "error": error.to_dict()}
    return {"role": "tool", "tool_call_id": tc.id, "content": json.dumps(payload)}


def _payload_hash(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _content_size(value: Any) -> int:
    raw = json.dumps(value, default=str).encode("utf-8")
    return len(raw)


def _is_action_claim(text: str) -> bool:
    lowered = text.lower()
    verbs = (
        "sent",
        "created",
        "updated",
        "scheduled",
        "notified",
        "assigned",
        "transitioned",
    )
    return any(v in lowered for v in verbs)


# ---------------------------------------------------------------------------
# Agent loop
# ---------------------------------------------------------------------------


class AgentLoop:
    def __init__(
        self, llm: LLMClient, registry: ToolRegistry, settings: Settings
    ) -> None:
        self._settings = settings
        self._llm = llm
        self._registry = registry
        self._max_steps = settings.max_agent_steps
        audit_path = settings.runtime_dir / settings.audit_log_file
        self._audit = AuditLogger(
            audit_path,
            enabled=settings.enable_audit_log,
        )
        self._cost_estimator = CostEstimator(settings)
        self._tracing = build_tracing_manager(settings)

    def run(self, user_message: str) -> Iterator[StepEvent]:
        """Run the ReAct loop; yields StepEvents including the final answer."""
        context = TaskContext.create(self._settings)
        metrics = TaskMetrics()
        log_contextvars.bind_contextvars(**context.as_dict())
        logger.info(
            "task_received",
            **context.as_dict(),
            prompt_hash=_payload_hash(user_message),
            prompt_size=len(user_message),
        )
        self._audit.emit(
            "task_received",
            context,
            payload={
                "prompt_hash": _payload_hash(user_message),
                "prompt_size": len(user_message),
            },
        )

        messages: list[dict[str, Any]] = [
            SYSTEM_PROMPT,
            {"role": "user", "content": user_message},
        ]
        seen_calls: set[tuple[str, str]] = set()
        outcome = "success"
        final_answer = "Done."
        successful_tool_results = 0

        def _event(
            event_type: EventType,
            *,
            content: str | None = None,
            name: str | None = None,
            args: dict[str, Any] | None = None,
            result: Any = None,
            error: str | None = None,
        ) -> StepEvent:
            return StepEvent(
                type=event_type,
                content=content,
                name=name,
                args=args or {},
                result=result,
                error=error,
                task_id=context.task_id,
                trace_id=context.trace_id,
            )

        try:
            with self._tracing.span(
                "agent.task_run",
                {
                    "task.id": context.task_id,
                    "trace.id": context.trace_id,
                    "agent.version": context.agent_version,
                    "llm.model": context.model_name,
                },
            ) as task_span:
                for step in range(self._max_steps):
                    logger.debug("agent_step", step=step, message_count=len(messages))
                    self._audit.emit(
                        "llm_called",
                        context,
                        payload={"step": step, "message_count": len(messages)},
                    )

                    # -- LLM call (retries handled inside OpenAIClient) ----------
                    with self._tracing.span(
                        "agent.llm_turn",
                        {
                            "agent.step": step,
                            "messages.count": len(messages),
                            "llm.model": context.model_name,
                        },
                    ) as llm_span:
                        try:
                            response = self._llm.chat(messages, self._registry.schemas())
                        except LLMError as exc:
                            outcome = "failure"
                            logger.error("llm_error", error=str(exc))
                            self._tracing.mark_error(llm_span, exc)
                            self._audit.emit(
                                "llm_returned",
                                context,
                                status="error",
                                payload={"step": step, "error": str(exc)},
                            )
                            yield _event("error", error=str(exc))
                            final_answer = f"LLM unavailable: {exc}"
                            yield _event("final_answer", content=final_answer)
                            return

                    metrics.llm_turns += 1
                    metrics.input_tokens += response.usage.input_tokens
                    metrics.output_tokens += response.usage.output_tokens
                    metrics.cached_tokens += response.usage.cached_tokens
                    turn_cost = self._cost_estimator.estimate(context.model_name, response.usage)
                    metrics.estimated_cost_usd += turn_cost
                    llm_span.set_attribute("llm.input_tokens", response.usage.input_tokens)
                    llm_span.set_attribute("llm.output_tokens", response.usage.output_tokens)
                    llm_span.set_attribute("llm.cached_tokens", response.usage.cached_tokens)
                    llm_span.set_attribute("llm.retry_count", response.retry_count)
                    llm_span.set_attribute("llm.turn_cost_usd", turn_cost)

                    self._audit.emit(
                        "llm_returned",
                        context,
                        payload={
                            "step": step,
                            "has_content": bool(response.content),
                            "tool_call_count": len(response.tool_calls),
                            "usage": {
                                "input_tokens": response.usage.input_tokens,
                                "output_tokens": response.usage.output_tokens,
                                "cached_tokens": response.usage.cached_tokens,
                            },
                            "estimated_turn_cost_usd": turn_cost,
                            "retry_count": response.retry_count,
                        },
                    )

                    # -- Reasoning text ------------------------------------------
                    if response.content:
                        logger.debug("reasoning", content=response.content[:120])
                        yield _event("reasoning", content=response.content)

                    # -- No tool calls → final answer ----------------------------
                    if not response.tool_calls:
                        final_answer = response.content or "Done."
                        if "?" in final_answer:
                            metrics.clarification_count += 1
                            outcome = "clarification"
                        else:
                            outcome = "success"
                        yield _event("final_answer", content=final_answer)
                        return

                    # -- Append full assistant message ONCE ----------------------
                    messages.append(_assistant_msg(response))

                    # -- Execute each tool call ----------------------------------
                    for tc in response.tool_calls:
                        # Guard: same tool + same args repeated → loop detected
                        key = (tc.name, json.dumps(tc.args, sort_keys=True))
                        if key in seen_calls:
                            outcome = "failure"
                            metrics.loop_detected_count += 1
                            logger.warning("loop_detected", tool=tc.name, args=tc.args)
                            self._audit.emit(
                                "task_guardrail",
                                context,
                                status="error",
                                payload={"code": "loop_detected", "tool": tc.name},
                            )
                            final_answer = "Loop detected: model repeated the same tool call."
                            task_span.set_attribute("guardrail.loop_detected", True)
                            yield _event("final_answer", content=final_answer)
                            return
                        seen_calls.add(key)

                        metrics.tool_calls += 1
                        self._audit.emit(
                            "tool_called",
                            context,
                            payload={
                                "step": step,
                                "tool": tc.name,
                                "args_hash": _payload_hash(tc.args),
                                "args_size": _content_size(tc.args),
                            },
                        )
                        yield _event("tool_call", name=tc.name, args=tc.args)
                        logger.info("tool_call", tool=tc.name, args=tc.args)

                        with self._tracing.span(
                            "agent.tool_call",
                            {
                                "agent.step": step,
                                "tool.name": tc.name,
                                "tool.args_size": _content_size(tc.args),
                            },
                        ) as tool_span:
                            try:
                                result = self._registry.dispatch(tc.name, tc.args)
                                logger.info("tool_result", tool=tc.name, result=result)
                                self._audit.emit(
                                    "tool_returned",
                                    context,
                                    payload={
                                        "step": step,
                                        "tool": tc.name,
                                        "result_size": _content_size(result),
                                        "result_hash": _payload_hash(result),
                                    },
                                )
                                tool_span.set_attribute("tool.status", "ok")
                                successful_tool_results += 1
                                yield _event("tool_result", name=tc.name, result=result)
                                messages.append(_tool_result_msg(tc, result))
                            except ToolError as exc:
                                outcome = "failure"
                                metrics.tool_errors += 1
                                if exc.code == "unknown_tool":
                                    metrics.unknown_tool_errors += 1
                                if exc.code == "invalid_arguments":
                                    metrics.invalid_arguments_errors += 1
                                logger.warning("tool_error", tool=tc.name, error=str(exc))
                                self._tracing.mark_error(tool_span, exc)
                                tool_span.set_attribute("tool.status", "error")
                                tool_span.set_attribute("tool.error_code", exc.code)
                                self._audit.emit(
                                    "tool_returned",
                                    context,
                                    status="error",
                                    payload={
                                        "step": step,
                                        "tool": tc.name,
                                        "error": exc.to_dict(),
                                    },
                                )
                                yield _event("tool_error", name=tc.name, error=str(exc))
                                # Send error back to the LLM so it can recover
                                messages.append(_tool_error_msg(tc, exc))

                # Max steps exhausted
                outcome = "failure"
                final_answer = "Max steps reached."
                yield _event("final_answer", content=final_answer)
        finally:
            summary = {
                "outcome": outcome,
                "duration_ms": metrics.duration_ms(),
                "llm_turns": metrics.llm_turns,
                "tool_calls": metrics.tool_calls,
                "successful_tool_results": successful_tool_results,
                "tool_errors": metrics.tool_errors,
                "clarification_count": metrics.clarification_count,
                "hallucination_suspected": (
                    successful_tool_results == 0
                    and _is_action_claim(final_answer)
                    and "?" not in final_answer
                ),
                "guardrails": metrics.guardrails(),
                "usage": {
                    "input_tokens": metrics.input_tokens,
                    "output_tokens": metrics.output_tokens,
                    "cached_tokens": metrics.cached_tokens,
                    "estimated_cost_usd": metrics.estimated_cost_usd,
                },
                "final_answer_hash": _payload_hash(final_answer),
            }
            logger.info("task_completed", **summary)
            self._audit.emit("task_completed", context, payload=summary)
            log_contextvars.clear_contextvars()
