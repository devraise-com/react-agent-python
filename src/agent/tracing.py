"""OpenTelemetry tracing setup and helpers with no-op fallback."""

from __future__ import annotations

import contextlib
import json
import logging
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.agent.config import Settings

logger = logging.getLogger(__name__)


class _NoopSpan:
    def set_attribute(self, key: str, value: Any) -> None:
        _ = (key, value)

    def record_exception(self, exc: BaseException) -> None:
        _ = exc

    def set_status(self, status: Any) -> None:
        _ = status


class _JsonlSpanExporter:
    """Append-only JSONL exporter: one line per span.

    Each span is written immediately on export — no buffering.  This avoids
    the ordering hazard of the previous grouped-trace design, where
    BatchSpanProcessor could flush a root span before all of its children had
    been buffered, producing incomplete traces on disk.
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.touch(exist_ok=True)
        self._lock = threading.Lock()

    def export(self, spans: Any) -> Any:
        now = datetime.now(timezone.utc).isoformat()
        records: list[str] = []
        for span in spans:
            parent = span.parent
            trace_id = f"{span.context.trace_id:032x}"
            status = getattr(span, "status", None)
            record: dict[str, Any] = {
                "timestamp": now,
                "trace_id": trace_id,
                "span_id": f"{span.context.span_id:016x}",
                "parent_span_id": (f"{parent.span_id:016x}" if parent else None),
                "name": span.name,
                "start_time_unix_nano": int(span.start_time),
                "end_time_unix_nano": int(span.end_time),
                "duration_ms": max(
                    (int(span.end_time) - int(span.start_time)) / 1_000_000, 0.0
                ),
                "attributes": dict(span.attributes),
                "status_code": str(getattr(status, "status_code", "")),
                "status_description": getattr(status, "description", ""),
            }
            records.append(json.dumps(record, ensure_ascii=True, default=str))
        if records:
            with self._lock:
                with self._path.open("a", encoding="utf-8") as f:
                    for line in records:
                        f.write(line + "\n")

        # Import locally to avoid hard dependency when tracing is disabled.
        from opentelemetry.sdk.trace.export import SpanExportResult  # type: ignore[import-not-found]

        return SpanExportResult.SUCCESS

    def shutdown(self) -> None:
        return None  # nothing buffered; no-op


def _resolve_runtime_file(base_dir: Path, filename_or_path: str) -> Path:
    path = Path(filename_or_path)
    if path.is_absolute():
        return path
    return base_dir / path


@dataclass
class TracingManager:
    enabled: bool
    _tracer: Any
    _status_code_error: Any | None = None
    _status_ctor: Any | None = None

    @contextlib.contextmanager
    def span(self, name: str, attributes: dict[str, Any] | None = None) -> Any:
        attrs = attributes or {}
        if not self.enabled or self._tracer is None:
            yield _NoopSpan()
            return
        with self._tracer.start_as_current_span(name) as span:
            for key, value in attrs.items():
                span.set_attribute(key, value)
            yield span

    def mark_error(self, span: Any, exc: BaseException) -> None:
        span.record_exception(exc)
        if self._status_code_error is not None and self._status_ctor is not None:
            span.set_status(self._status_ctor(self._status_code_error, str(exc)))


def build_tracing_manager(settings: Settings) -> TracingManager:
    if not settings.enable_tracing:
        return TracingManager(enabled=False, _tracer=None)

    try:
        from opentelemetry import trace  # type: ignore[import-not-found]
        from opentelemetry.sdk.resources import (  # type: ignore[import-not-found]
            Resource,
        )
        from opentelemetry.sdk.trace import (  # type: ignore[import-not-found]
            TracerProvider,
        )
        from opentelemetry.sdk.trace.export import (
            BatchSpanProcessor,
            ConsoleSpanExporter,
        )
        from opentelemetry.trace import (  # type: ignore[import-not-found]
            Status,
            StatusCode,
        )
    except Exception as exc:  # pragma: no cover - environment-dependent
        logger.warning("tracing_disabled_import_error: %s", str(exc))
        return TracingManager(enabled=False, _tracer=None)

    resource = Resource.create({"service.name": settings.tracing_service_name})
    provider = TracerProvider(resource=resource)

    exporter = settings.tracing_exporter.strip().lower()
    if exporter == "file":
        trace_path = _resolve_runtime_file(settings.runtime_dir, settings.tracing_file)
        span_exporter = _JsonlSpanExporter(trace_path)
    elif exporter == "otlp" and settings.tracing_otlp_endpoint.strip():
        try:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter  # type: ignore[import-not-found]

            span_exporter = OTLPSpanExporter(endpoint=settings.tracing_otlp_endpoint)
        except Exception as exc:  # pragma: no cover - environment-dependent
            logger.warning("tracing_otlp_exporter_unavailable: %s", str(exc))
            span_exporter = ConsoleSpanExporter()
    else:
        span_exporter = ConsoleSpanExporter()

    processor = BatchSpanProcessor(span_exporter)
    provider.add_span_processor(processor)
    trace.set_tracer_provider(provider)
    tracer = trace.get_tracer(settings.tracing_service_name)
    return TracingManager(
        enabled=True,
        _tracer=tracer,
        _status_code_error=StatusCode.ERROR,
        _status_ctor=Status,
    )
