# Design Decisions

## 1. In-process mock services instead of an HTTP server

**Decision:** Mock services are plain Python classes (`SlackService`, `CalendarService`, etc.) called directly by tool functions. No FastAPI server, no HTTP.

**Why:** The spec says "set up mock server/servers and use them", which I interpreted as requiring realistic simulation (state, validation, error injection) rather than requiring HTTP transport. Running an embedded HTTP server adds process management, port conflicts, and test complexity for no architectural benefit in a single-user CLI tool. The mock layer is still a realistic simulation — it has persistent JSON state, full parameter validation, and error injection — it just communicates via function calls instead of HTTP.

**Trade-off:** The demo is less "look I set up a real HTTP server" but the code is simpler, easier to test, and harder to break.

---

## 2. ReAct loop built from scratch (no LangChain/AutoGen)

**Decision:** `AgentLoop` in `src/agent/loop.py` implements the full Reason→Act→Observe cycle manually.

**Why:** Required by the spec. Also, high-level frameworks add significant hidden complexity and make it harder to reason about exactly what messages are being sent to the LLM. The hand-rolled loop is ~80 lines, fully transparent, and easy to extend.

---

## 3. OpenAI GPT-4o as the default model

**Decision:** Use `openai` SDK with GPT-4o default, configurable via `OPENAI_MODEL` env var.

**Why:** As specified. GPT-4o has excellent native tool-use support, and the OpenAI Python SDK handles streaming, retries, and tool-call serialisation cleanly.

---

## 4. Tool schema generation via function introspection

**Decision:** `ToolRegistry.register()` builds OpenAI tool schemas by inspecting function signatures and docstrings at registration time.

**Why:** Avoids maintaining schemas in two places (Python signature and JSON). The docstring becomes the tool description, and parameter types become the JSON Schema types. This makes adding a new tool a one-step operation.

**Trade-off:** Complex types (nested Pydantic models) need manual schema work. For this project, all tool parameters are primitives or `list[str]`, so introspection is sufficient.

---

## 5. Closure-based tool registration

**Decision:** Each tool module exports a `register_X_tools(service, registry)` function that defines inner functions (closures) and registers them.

**Why:** The closure captures the service instance cleanly without global state. Tools are thin wrappers — one line each — with no service-level logic leaking into the tool layer. This makes the tool layer trivially testable: inject a mock service, verify the right service method was called.

---

## 6. JSON file persistence for mock services

**Decision:** `JsonStore` writes/reads a JSON file per service. State survives restarts.

**Why:** Required by the spec ("state is persisted between calls"). JSON files are human-readable, easy to inspect/reset for demos, and require no external dependencies. `threading.Lock` guards the file for correctness even if a future version introduces threads.

---

## 7. Error injection via environment variables

**Decision:** `MOCK_ERROR_RATE` (random rate) and `MOCK_FORCE_ERROR` (`<service>:<code>`) control error injection at startup.

**Why:** Env vars are easy to set without code changes and work naturally with the `.env` file. `MOCK_FORCE_ERROR=slack:rate_limit` lets an interviewer demonstrate error handling by restarting the agent with a single env var change.

---

## 8. `tenacity` for LLM retry

**Decision:** `OpenAIClient.chat()` is decorated with `@retry` from tenacity, targeting `RateLimitError` and `APITimeoutError` with exponential backoff (2s min, 30s max, 4 attempts).

**Why:** Transient rate limits are expected in production use of OpenAI. Tenacity integrates cleanly with the decorator pattern and is transparent to the agent loop — the loop only sees `LLMError` if all retries are exhausted.

---

## 9. `structlog` for structured logging

**Decision:** All application logging uses `structlog` bound to stdlib via `ProcessorFormatter`. DEBUG emits JSON; INFO+ emits human-readable console output.

**Why:** Structured logging makes log aggregation and debugging in production far easier. Two render modes cover both machine-readable (log files/aggregators) and human-readable (development) use cases with a single env var change (`LOG_LEVEL=DEBUG`).

---

## 10. Loop-detection guard

**Decision:** `AgentLoop` tracks `(tool_name, json.dumps(args, sort_keys=True))` in `seen_calls` across all steps. Repeated identical call → immediate termination.

**Why:** Models can get stuck in retry loops when a tool fails. Without this guard the agent would exhaust `MAX_AGENT_STEPS` silently. `sort_keys=True` ensures key-ordering variations in the args dict don't defeat the check.
