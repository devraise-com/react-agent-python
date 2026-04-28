"""Unit tests for tracing helpers."""

from pathlib import Path

from src.agent.config import Settings
from src.agent.tracing import _resolve_runtime_file, build_tracing_manager


def test_tracing_disabled_manager_is_noop() -> None:
    settings = Settings(enable_tracing=False)
    manager = build_tracing_manager(settings)
    assert manager.enabled is False
    with manager.span("test") as span:
        span.set_attribute("x", 1)


def test_resolve_runtime_file_relative_and_absolute() -> None:
    base = Path("runtime")
    rel = _resolve_runtime_file(base, "traces.jsonl")
    assert rel == base / "traces.jsonl"

    abs_path = Path("/tmp/trace-file.jsonl")
    resolved = _resolve_runtime_file(base, str(abs_path))
    assert resolved == abs_path
