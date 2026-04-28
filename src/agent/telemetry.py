"""Runtime telemetry: task context, metrics, cost accounting, and audit sink."""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.agent.config import Settings
from src.agent.llm_client import LLMUsage


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class TaskContext:
    task_id: str
    trace_id: str
    session_id: str
    user_id: str
    environment: str
    agent_version: str
    model_provider: str
    model_name: str

    @classmethod
    def create(cls, settings: Settings) -> "TaskContext":
        session_id = settings.session_id.strip() or f"session-{uuid4().hex[:12]}"
        user_id = settings.current_user.strip() or "anonymous"
        return cls(
            task_id=str(uuid4()),
            trace_id=str(uuid4()),
            session_id=session_id,
            user_id=user_id,
            environment=settings.environment,
            agent_version=settings.agent_version,
            model_provider="openai",
            model_name=settings.openai_model,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "trace_id": self.trace_id,
            "session_id": self.session_id,
            "user_id": self.user_id,
            "environment": self.environment,
            "agent_version": self.agent_version,
            "model_provider": self.model_provider,
            "model_name": self.model_name,
        }


@dataclass
class TaskMetrics:
    start_ts: float = field(default_factory=time.time)
    llm_turns: int = 0
    tool_calls: int = 0
    tool_errors: int = 0
    unknown_tool_errors: int = 0
    invalid_arguments_errors: int = 0
    loop_detected_count: int = 0
    clarification_count: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    estimated_cost_usd: float = 0.0

    def duration_ms(self) -> int:
        return int((time.time() - self.start_ts) * 1000)

    def guardrails(self) -> dict[str, float]:
        denom = max(self.tool_calls, 1)
        llm_denom = max(self.llm_turns, 1)
        misuse = self.unknown_tool_errors + self.invalid_arguments_errors
        return {
            "unknown_tool_rate": self.unknown_tool_errors / denom,
            "invalid_arguments_rate": self.invalid_arguments_errors / denom,
            "tool_misuse_rate": misuse / denom,
            "loop_detected_rate": self.loop_detected_count / llm_denom,
        }


class CostEstimator:
    """Estimate per-task cost using a simple versioned model pricing table."""

    _PRICING_USD_PER_MILLION: dict[str, dict[str, float]] = {
        "gpt-4o": {"input": 5.0, "output": 15.0, "cached_input": 1.25},
        "gpt-4o-mini": {"input": 0.15, "output": 0.6, "cached_input": 0.075},
    }

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def estimate(self, model_name: str, usage: LLMUsage) -> float:
        pricing = self._PRICING_USD_PER_MILLION.get(model_name)
        if pricing is None:
            pricing = {
                "input": self._settings.cost_input_per_million_tokens,
                "output": self._settings.cost_output_per_million_tokens,
                "cached_input": self._settings.cost_cached_input_per_million_tokens,
            }
        input_billable = max(usage.input_tokens - usage.cached_tokens, 0)
        return (
            (input_billable / 1_000_000) * pricing["input"]
            + (usage.cached_tokens / 1_000_000) * pricing["cached_input"]
            + (usage.output_tokens / 1_000_000) * pricing["output"]
        )


class AuditLogger:
    """Append-only JSONL audit sink."""

    def __init__(self, path: Path, enabled: bool = True) -> None:
        self._path = path
        self._enabled = enabled
        self._lock = threading.Lock()
        if self._enabled:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.touch(exist_ok=True)

    def emit(
        self,
        event_type: str,
        context: TaskContext,
        *,
        status: str = "ok",
        payload: dict[str, Any] | None = None,
    ) -> None:
        if not self._enabled:
            return
        event = {
            "timestamp": utc_now_iso(),
            "event_type": event_type,
            "status": status,
            **context.as_dict(),
            "payload": payload or {},
        }
        line = json.dumps(event, ensure_ascii=True, separators=(",", ":"))
        with self._lock:
            with self._path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
