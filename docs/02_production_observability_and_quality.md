# Production Readiness Plan: Observability, Audit, Cost, and Quality

## 1. Scope and Objective

This document defines production requirements and rollout criteria for the agent in two areas:

1. Operational observability: audit trail, end-to-end tracing, and per-task cost control.
2. Production quality management: golden evaluations, regression gates, and hallucination/tool-misuse monitoring.

The goal is to make releases measurable, reversible, and governed by explicit quality and cost thresholds.

## 2. Production Requirements: Observability and Audit

### 2.1 Canonical unit of execution

Every user request must be represented as a `task_run`.  
A `task_run` includes:

1. One or more `llm_turn` events.
2. Zero or more `tool_call` events.
3. Exactly one terminal `task_outcome` event.

### 2.2 Required correlation identifiers

All runtime events must include:

1. `task_id` (UUID).
2. `trace_id` (UUID, shared across all events in the run).
3. `session_id`.
4. `user_id` (or service principal id).
5. `environment` (`dev`, `stage`, `prod`).
6. `agent_version` (git SHA + semantic version).
7. `model_provider` and `model_name`.

No event should be emitted without `task_id` and `trace_id`.

### 2.3 Audit trail requirements

The system must emit append-only audit records for:

1. `task_received`.
2. `llm_called`.
3. `llm_returned`.
4. `tool_called`.
5. `tool_returned`.
6. `task_completed`.

Each record must include:

1. Event timestamp (UTC).
2. Event type.
3. Correlation identifiers.
4. Status (`ok`, `error`, `clarification`, `aborted`).
5. Redacted payload metadata (size/hash/classification, not raw sensitive content by default).

Compliance constraints:

1. Default logs must not contain raw PII.
2. Raw prompt/response capture, if enabled, must be separately protected and retention-controlled.
3. Audit events are immutable (append-only storage policy).

### 2.4 Tracing requirements

Tracing must be implemented with a root span per `task_run` and child spans for:

1. Each `llm_turn`.
2. Each `tool_call`.
3. Downstream tool backend operations (when HTTP/DB integrations are introduced).

Each span must capture:

1. `duration_ms`.
2. `status_code`.
3. `retry_count`.
4. Input/output payload size metrics.

Recommended stack:

1. OpenTelemetry instrumentation.
2. Trace export to Jaeger/Tempo.
3. Metrics export to Prometheus-compatible backend.

### 2.5 Cost accounting requirements

For every `task_run`, the platform must compute and persist:

1. `input_tokens`.
2. `output_tokens`.
3. `cached_tokens` (if available).
4. `estimated_cost_usd`.

`estimated_cost_usd` must be calculated from a versioned pricing table keyed by provider/model/date.

Required aggregated metrics:

1. `cost_per_task` (p50/p95/p99).
2. `cost_per_successful_task`.
3. `tokens_per_task`.
4. `cost_anomaly_rate`.

Alerting requirements:

1. Trigger alert when weekly `cost_per_task` increases by >30% without a matching quality gain.
2. Trigger alert when `tokens_per_task` increases by >25% week-over-week.

### 2.6 SLOs and operational dashboards

Baseline SLO targets:

1. `task_success_rate >= 97%` on valid user intents.
2. `p95 task_latency <= 12s`.
3. `tool_error_rate <= 3%` (excluding controlled fault-injection environments).
4. `clarification_rate` must remain within an agreed operational band.

Production dashboard must expose:

1. Success/failure/clarification trends.
2. Latency p50/p95 by task and by tool.
3. Cost trends by release and model.
4. Top error codes and top failing tools.
5. Hallucination and tool-misuse trends (defined below).

## 3. Production Requirements: Quality Evaluation and Release Gates

### 3.1 Quality dimensions

All evaluations must score the following dimensions:

1. Tool routing correctness.
2. Tool argument correctness.
3. Execution robustness under failures/retries.
4. Final response grounding (no fabricated actions/results).

### 3.2 Golden suite requirements

A versioned golden suite must be maintained in-repo and run in CI.

The suite must include:

1. Happy-path workflows.
2. Ambiguous requests requiring clarification.
3. Tool failure and recovery scenarios.
4. Adversarial prompts targeting tool misuse.

Each case must define machine-checkable expectations:

1. Expected tool sequence.
2. Expected argument constraints.
3. Expected outcome class.
4. Maximum step count and maximum cost budget.

### 3.3 Regression gate policy

No release to production is allowed unless all gates pass:

1. Golden suite pass rate at or above baseline threshold.
2. No statistically significant regression in `task_success_rate`.
3. No increase in `tool_misuse_rate`.
4. No increase in `hallucination_rate`.
5. No increase in `cost_per_task` above approved budget.
6. No increase in p95 latency above approved budget.

If any gate fails, deployment is blocked automatically.

### 3.4 Hallucination and tool-misuse metrics

`tool_misuse_rate` must count at least:

1. Wrong tool selected for a known intent class.
2. Invalid argument attempts (`invalid_arguments`).
3. Redundant tool calls that do not contribute to outcome.

`hallucination_rate` must count at least:

1. Final answers claiming actions not supported by tool results.
2. Final answers referencing non-existent IDs/entities/results.

Measurement policy:

1. Deterministic rule-based checks over event logs are the primary signal.
2. LLM-as-judge is secondary only.
3. Weekly human review sample is required for calibration.

### 3.5 Online evaluation and rollout controls

All production releases must use staged exposure:

1. Canary rollout (default: 5% traffic).
2. A/B comparison against previous stable version.
3. Automatic rollback on guardrail breach.

Required guardrails:

1. `unknown_tool_rate`.
2. `invalid_arguments_rate`.
3. `loop_detected_rate`.
4. `user_rephrase_rate` (proxy for low answer quality).

## 4. Rollout Plan to Production Standard

### Phase 1: Instrumentation Foundation (1-2 weeks)

1. Add `task_id` and `trace_id` to all loop/runtime events.
2. Implement canonical event schema.
3. Capture token usage and estimated task cost.
4. Deliver baseline production dashboard.

Exit criteria:

1. Every task is traceable end-to-end by `task_id`.
2. Cost and latency are visible per task and per release.

### Phase 2: Quality Harness and Gates (1-2 weeks)

1. Implement versioned golden suite.
2. Build automated evaluator and CI regression gates.
3. Add hallucination and tool-misuse metric computation.

Exit criteria:

1. Any model/prompt/tool change is blocked on gate failure.
2. Quality regressions are detected pre-release.

### Phase 3: Controlled Production Rollout (2-4 weeks)

1. Enable canary + A/B rollout path.
2. Implement rollback automation on guardrail breach.
3. Establish weekly quality/cost review cadence.

Exit criteria:

1. Release decisions are data-driven and reversible.
2. Operational and quality SLOs are continuously monitored.

## 5. Definition of Production Readiness

The agent is considered production-ready when all conditions are met:

1. Any incident can be reconstructed from immutable audit and trace data.
2. Cost per task is measured, trended, and alert-driven.
3. Every release is gated by golden/regression quality checks.
4. Hallucination and tool-misuse are measured as first-class metrics.
5. Canary and rollback controls are active for every production deployment.

---

## 6. Implementation Reference

This section documents what is implemented, how to configure it, and how to
operate it. Sections 1–5 above are requirements; this section is the living
usage guide for the shipped code.

### 6.1 Runtime file layout

All runtime artefacts are written under `RUNTIME_DIR` (default: `runtime/`).

```
runtime/
  agent.log            # structured JSON log (structlog)
  audit_events.jsonl   # append-only audit trail (one JSON object per line)
  traces.jsonl         # OTel spans (one JSON object per span, if file exporter)
```

### 6.2 Configuration

All settings are loaded from environment variables or a `.env` file.
Copy `.env.example` and adjust:

```bash
cp .env.example .env
```

| Variable | Default | Description |
|---|---|---|
| `RUNTIME_DIR` | `runtime` | Base directory for all runtime files |
| `ENVIRONMENT` | `dev` | Environment tag embedded in every event (`dev`/`stage`/`prod`) |
| `AGENT_VERSION` | `0.1.0` | Version string embedded in every event |
| `SESSION_ID` | _(auto)_ | Session identifier; auto-generated UUID if empty |
| `ENABLE_AUDIT_LOG` | `true` | Write append-only audit JSONL |
| `AUDIT_LOG_FILE` | `audit_events.jsonl` | File name under `RUNTIME_DIR` |
| `ENABLE_TRACING` | `false` | Enable OpenTelemetry tracing |
| `TRACING_EXPORTER` | `file` | `file` · `console` · `otlp` |
| `TRACING_FILE` | `traces.jsonl` | File name under `RUNTIME_DIR` (file exporter only) |
| `TRACING_OTLP_ENDPOINT` | _(empty)_ | e.g. `http://localhost:4318/v1/traces` |
| `TRACING_SERVICE_NAME` | `react-agent-python` | OTel `service.name` resource attribute |
| `COST_INPUT_PER_MILLION_TOKENS` | `5.0` | Override input price in USD/M tokens |
| `COST_OUTPUT_PER_MILLION_TOKENS` | `15.0` | Override output price in USD/M tokens |
| `COST_CACHED_INPUT_PER_MILLION_TOKENS` | `1.25` | Override cached-input price in USD/M tokens |

Known model prices (`gpt-4o`, `gpt-4o-mini`) are hardcoded in
`src/agent/telemetry.py:CostEstimator` and take precedence over the env-var
overrides. The env-var overrides apply to any other model name.

### 6.3 Audit log format

Each line in `audit_events.jsonl` is a self-contained JSON object:

```json
{
  "timestamp": "2026-04-28T10:00:00.123456+00:00",
  "event_type": "task_completed",
  "status": "ok",
  "task_id": "uuid4",
  "trace_id": "uuid4",
  "session_id": "session-abc123",
  "user_id": "john.doe",
  "environment": "prod",
  "agent_version": "0.1.0",
  "model_provider": "openai",
  "model_name": "gpt-4o",
  "payload": {
    "outcome": "success",
    "duration_ms": 3400,
    "llm_turns": 3,
    "tool_calls": 2,
    "successful_tool_results": 2,
    "tool_errors": 0,
    "clarification_count": 0,
    "hallucination_suspected": false,
    "guardrails": {
      "unknown_tool_rate": 0.0,
      "invalid_arguments_rate": 0.0,
      "tool_misuse_rate": 0.0,
      "loop_detected_rate": 0.0
    },
    "usage": {
      "input_tokens": 1200,
      "output_tokens": 400,
      "cached_tokens": 100,
      "estimated_cost_usd": 0.0075
    },
    "final_answer_hash": "sha256hex"
  }
}
```

Emitted event types in order: `task_received` → `llm_called` →
`llm_returned` → `tool_called` → `tool_returned` → (repeat) →
`task_completed`. `task_guardrail` is emitted on loop detection.

`outcome` values: `success` · `failure` · `clarification`.

`hallucination_suspected` is a heuristic rule: set to `true` when no tool
produced a successful result but the final answer uses action-claiming verbs
(`sent`, `created`, `updated`, `scheduled`, …) without a question mark.

### 6.4 Trace file format

When `TRACING_EXPORTER=file`, each span is written as one line in
`traces.jsonl`:

```json
{
  "timestamp": "2026-04-28T10:00:00+00:00",
  "trace_id": "032hex",
  "span_id": "016hex",
  "parent_span_id": "016hex or null",
  "name": "agent.tool_call",
  "start_time_unix_nano": 1714298400000000000,
  "end_time_unix_nano":   1714298401500000000,
  "duration_ms": 1500.0,
  "attributes": { "tool.name": "slack_send_message", "tool.status": "ok" },
  "status_code": "StatusCode.OK",
  "status_description": ""
}
```

Span names: `agent.task_run` (root) · `agent.llm_turn` · `agent.tool_call`.

To ship spans to Jaeger or Tempo instead, set:
```
ENABLE_TRACING=true
TRACING_EXPORTER=otlp
TRACING_OTLP_ENDPOINT=http://localhost:4318/v1/traces
```

### 6.5 Computing metrics from the audit log

`src/agent/metrics.py` provides pure functions over a list of
`task_completed` events. All functions accept the output of
`load_task_completed_events(path)`:

```python
from pathlib import Path
from src.agent.metrics import load_task_completed_events, get_success_rate, get_p95_latency

events = load_task_completed_events(Path("runtime/audit_events.jsonl"))
print(get_success_rate(events))      # float in [0, 1]
print(get_p95_latency(events))       # milliseconds
print(get_error_rate(events))
print(get_avg_tokens_per_task(events))
print(get_steps_per_task(events))
print(get_tool_error_rate(events))
```

### 6.6 Running the CI quality gate check

`scripts/check_quality_gates.py` is the CLI entry point for CI pipelines.
It reads the audit log, evaluates all gates, prints a report, and exits
with code `1` if any gate is breached.

```bash
# Check with default SLO thresholds (success >= 97%, cost <= $0.05/task, …)
python scripts/check_quality_gates.py runtime/audit_events.jsonl

# Override individual thresholds
python scripts/check_quality_gates.py runtime/audit_events.jsonl \
    --min-success-rate 0.95 \
    --max-avg-cost-per-task-usd 0.10
```

Example output (all gates pass):

```
Loaded 42 task_completed events from runtime/audit_events.jsonl

--- Quality Gate Metrics ---
  Task Count                       42.0000
  Success Rate                      0.9762
  Hallucination Rate                0.0000
  Avg Cost Per Task Usd             0.0082
  Avg Tool Misuse Rate              0.0047
  Avg Loop Detected Rate            0.0000

--- Thresholds ---
  Min success rate                  0.9700
  Max tool misuse rate              0.0300
  Max loop detected rate            0.0200
  Max hallucination rate            0.0200
  Max avg cost per task (USD)       0.0500

All quality gates PASSED.
```

Exit code `0` = all gates pass. Exit code `1` = one or more breaches (CI fails).

Typical CI integration (GitHub Actions example):

```yaml
- name: Quality gate check
  run: python scripts/check_quality_gates.py runtime/audit_events.jsonl
```

### 6.7 Golden test suite

The golden test suite is in `tests/golden/test_golden_suite.py`. It covers
the four mandatory scenario types from section 3.2 (plus a multi-step
variant) using a scripted LLM — no real API call is made.

```bash
# Run the golden suite only
pytest tests/golden/ -v

# Run the full test suite including goldens
pytest
```

Each `GoldenCase` defines:

| Field | Type | Description |
|---|---|---|
| `name` | `str` | Unique scenario identifier |
| `prompt` | `str` | User input fed to the agent |
| `llm_script` | `list[LLMResponse]` | Scripted LLM turn sequence |
| `expected_tool_sequence` | `list[str]` | Ordered tool names expected to be called |
| `expected_outcome` | `str` | `"success"` · `"failure"` · `"clarification"` |
| `max_steps` | `int` | Maximum LLM turns allowed |
| `max_cost_usd` | `float` | Maximum estimated cost per task in USD |

Current golden cases:

| Name | Scenario type | Expected outcome |
|---|---|---|
| `happy_path_slack_send` | Happy path (single tool) | `success` |
| `happy_path_jira_then_slack` | Happy path (multi-step) | `success` |
| `clarification_ambiguous_request` | Clarification | `clarification` |
| `tool_failure_recovery` | Failure + recovery | `success` |
| `adversarial_loop_detection` | Adversarial (loop guard) | `failure` |

To add a new golden case, append a `GoldenCase` to the `GOLDEN_CASES` list
in `tests/golden/test_golden_suite.py`.

### 6.8 Modules at a glance

| Module | Role |
|---|---|
| `src/agent/telemetry.py` | `TaskContext`, `TaskMetrics`, `CostEstimator`, `AuditLogger` |
| `src/agent/tracing.py` | `TracingManager`, `build_tracing_manager`, JSONL span exporter |
| `src/agent/metrics.py` | Post-hoc analytics functions over audit JSONL |
| `src/agent/quality_gates.py` | `GateThresholds`, `GateResult`, `evaluate_quality_gates` |
| `scripts/check_quality_gates.py` | CI gate runner CLI |
| `tests/golden/test_golden_suite.py` | Parametrised golden test suite |
