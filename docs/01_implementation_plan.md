# Implementation Plan — ReAct AI Agent (react-agent-python)

## Context

Build a CLI-based ReAct AI agent for workplace automation from scratch. The agent accepts natural-language commands and executes them by calling mocked external APIs (Slack, Google Calendar, Jira, Email). No high-level agent frameworks (LangChain, etc.) — only the OpenAI SDK and helper libraries.

Graded criteria: agent correctness (30%), architecture (25%), mock API quality (20%), tests (15%), documentation (10%).

---

## Final Directory Structure

```
react-agent-python/
├── agent.py                       # CLI entry point (`python agent.py`)
├── pyproject.toml                 # deps, mypy, pytest, coverage config
├── .env.example                   # all env vars documented
├── .gitignore
├── README.md
├── DECISIONS.md
├── docs/
│   ├── 00_initial_task.md         # original assignment
│   └── 01_implementation_plan.md  # this plan
│
├── src/
│   ├── __init__.py
│   ├── agent/
│   │   ├── __init__.py
│   │   ├── config.py              # pydantic-settings: load .env, typed settings
│   │   ├── llm_client.py          # OpenAI SDK wrapper; retry/backoff; tool-call formatting
│   │   └── loop.py                # ReAct loop: Reason → Act → Observe → repeat
│   │
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── registry.py            # ToolRegistry: register fns, auto-gen JSON Schema, dispatch
│   │   ├── base.py                # ToolResult dataclass, ToolError exception
│   │   ├── slack.py               # send_message, list_channels, search_messages
│   │   ├── calendar.py            # create_event, list_events, find_free_slot
│   │   ├── jira.py                # create_issue, get_issue, transition_issue
│   │   └── email.py               # send_email, search_email
│   │
│   ├── mock_services/
│   │   ├── __init__.py
│   │   ├── base.py                # MockServiceError, ErrorInjector (MOCK_ERROR_RATE / MOCK_FORCE_ERROR)
│   │   ├── persistence.py         # JsonStore: thread-safe JSON read/write per service
│   │   ├── slack_service.py       # SlackService: send_message, list_channels, search_messages
│   │   ├── calendar_service.py    # CalendarService: create_event, list_events, find_free_slot
│   │   ├── jira_service.py        # JiraService: create_issue, get_issue, transition_issue
│   │   └── email_service.py       # EmailService: send_email, search_email
│   │
│   └── cli/
│       ├── __init__.py
│       └── interface.py           # rich-based REPL; renders reasoning steps + tool calls + final answer
│
├── tests/
│   ├── conftest.py                # fixtures: mock LLM, tmp data dir, pre-seeded services
│   ├── unit/
│   │   ├── test_loop.py           # AgentLoop with scripted LLM responses
│   │   ├── test_registry.py       # schema generation, dispatch, unknown-tool error
│   │   ├── test_llm_client.py     # retry logic, tool-call formatting
│   │   ├── test_slack_tools.py    # tool fns with mocked SlackService
│   │   ├── test_calendar_tools.py
│   │   ├── test_jira_tools.py
│   │   └── test_email_tools.py
│   └── integration/
│       ├── test_mock_services.py  # service-level contract tests (state, validation, error injection)
│       └── test_scenarios.py      # scenarios A–D: scripted LLM + real in-process services
│
└── data/                          # runtime JSON state files; seeded on first run
    └── .gitkeep
```

---

## Technology Stack

| Concern | Library | Notes |
|---|---|---|
| LLM | `openai` | GPT-4o default, configurable via `OPENAI_MODEL` |
| Mock services | plain Python classes | In-process; no HTTP server needed |
| Validation | `pydantic` v2 | Request/response models for all service methods |
| Config | `pydantic-settings` + `python-dotenv` | Typed, env-aware settings object |
| CLI | `rich` | Live panel for ReAct steps, tool call display |
| Logging | `structlog` | JSON in DEBUG, human-readable in INFO |
| Retry / backoff | `tenacity` | Used in `OpenAIClient` for `RateLimitError` / `APITimeoutError` |
| Tests | `pytest` + `pytest-cov` | No HTTP mocking needed; services injected directly |
| Type checking | `mypy` (strict) | Configured in pyproject.toml |

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│  CLI  (agent.py + src/cli/interface.py)              │  rich REPL
├─────────────────────────────────────────────────────┤
│  Agent Loop  (src/agent/loop.py)                     │  ReAct: reason→act→observe
├─────────────────────────────────────────────────────┤
│  LLM Client  (src/agent/llm_client.py)               │  OpenAI SDK, retry/backoff
├──────────────────┬──────────────────────────────────┤
│  Tool Registry   │  (src/tools/registry.py)          │  schema gen, dispatch
│  ├ slack.py      │  ├ calendar.py                    │  thin wrappers — call services
│  ├ jira.py       │  └ email.py                       │
├──────────────────┴──────────────────────────────────┤
│  Mock Services  (src/mock_services/)                 │  in-process, stateful
│  SlackService · CalendarService · JiraService        │  Pydantic validation
│  EmailService · JsonStore · ErrorInjector            │  JSON persistence, error inject
└─────────────────────────────────────────────────────┘
```

---

## Key Components

### 1. `src/agent/config.py`
`Settings` (pydantic-settings) with fields:
- `OPENAI_API_KEY`, `OPENAI_MODEL="gpt-4o"`
- `MOCK_ERROR_RATE=0.0`, `MOCK_FORCE_ERROR=""`
- `LOG_LEVEL="INFO"`, `LOG_FILE=""`
- `MAX_AGENT_STEPS=20`, `CURRENT_USER=""`
- `DATA_DIR="data"`

### 2. `src/agent/llm_client.py`

Data classes defined here and used across `loop.py`:
```python
@dataclass
class ToolCall:
    id: str           # tool_call_id from OpenAI — required in tool_result messages
    name: str
    args: dict[str, Any]

@dataclass
class LLMResponse:
    content: str | None       # None when model goes straight to tool_calls
    tool_calls: list[ToolCall] # empty list when model returns a final answer
```

- `LLMClient` abstract base with `chat(messages, tools) -> LLMResponse`
- `OpenAIClient(LLMClient)`: wraps `openai.OpenAI`; converts registry schemas → OpenAI `tools` format; retries on `RateLimitError` / `APITimeoutError` with exponential backoff (tenacity)

### 3. `src/agent/loop.py` — System Prompt

The system prompt is defined as a constant in `loop.py` and injected as the first `{"role": "system"}` message in every conversation. It governs four behaviours:

```
You are a workplace automation assistant. You help users perform actions
across Slack, Google Calendar, Jira, and Email by calling the available tools.

Rules:
1. If the user's request is ambiguous or missing required details (e.g. "send
   an update" with no channel, content, or recipient specified), ask ONE
   concise clarifying question. Do NOT call any tool until you have enough
   information.
2. Only call a tool when all required parameters are known. If a tool returns
   an error, explain what went wrong and suggest what the user can do next.
3. After completing all actions, present a brief summary of what was done
   (which tools were called and what the outcomes were).
4. Never fabricate tool results. If a tool call fails, report the failure
   honestly.
```

### 4. `src/agent/loop.py` — ReAct Loop
```python
def run(user_message: str) -> Generator[StepEvent, None, AgentResult]:
    messages = [system_prompt, {"role": "user", "content": user_message}]
    seen_calls: set[tuple[str, str]] = set()
    for step in range(MAX_AGENT_STEPS):
        # LLM errors after all retries (tenacity in llm_client.py) are caught here
        try:
            response = llm.chat(messages, tools=registry.schemas())
        except LLMError as e:
            yield StepEvent(type="error", content=str(e))
            return AgentResult(answer=f"LLM unavailable: {e}", steps=step, error=True)

        if response.content:  # may be None when model goes straight to tool_calls
            yield StepEvent(type="reasoning", content=response.content)
        if not response.tool_calls:
            return AgentResult(answer=response.content or "Done.", steps=step)

        # Append full assistant message (content + all tool_calls) ONCE
        messages.append(assistant_msg(response))  # {"role": "assistant", "content": ..., "tool_calls": [...]}
        for tc in response.tool_calls:
            # Guard against infinite tool loop (same tool + same args repeated)
            key = (tc.name, json.dumps(tc.args, sort_keys=True))
            if key in seen_calls:
                return AgentResult(answer="Loop detected: model repeated the same tool call.", steps=step, error=True)
            seen_calls.add(key)
            yield StepEvent(type="tool_call", name=tc.name, args=tc.args)
            try:
                result = registry.dispatch(tc.name, tc.args)
                yield StepEvent(type="tool_result", name=tc.name, result=result)
                messages.append(tool_result_msg(tc, result))
            except ToolError as e:
                # Send error back to LLM so it can recover (retry, rephrase, or explain)
                yield StepEvent(type="tool_error", name=tc.name, error=str(e))
                messages.append(tool_error_msg(tc, str(e)))  # {"role": "tool", "tool_call_id": tc.id, "content": "Error: ..."}

    return AgentResult(answer="Max steps reached.", steps=MAX_AGENT_STEPS)
```

### 5. `src/tools/registry.py`
- `ToolRegistry`: `name → (callable, openai_tool_schema)`
- `@registry.register` decorator: builds JSON Schema from the function's Pydantic input model + docstring
- `registry.schemas()` → list of dicts for OpenAI `tools=` param
- `registry.dispatch(name, args)` → validates args, calls fn, wraps errors in `ToolError`

### 6. Mock Services — `src/mock_services/`

**`persistence.py` — `JsonStore`**
- `JsonStore(path: Path)` — `read() / write(data) / update(fn)`; simple file-based persistence with a lock for safety
- Each service owns one file: `data/slack.json`, `data/calendar.json`, etc.
- Seed defaults written on first instantiation if file missing

**`base.py` — `ErrorInjector`**
- `maybe_raise(service: str)` — checks `MOCK_ERROR_RATE` (random) and `MOCK_FORCE_ERROR` (targeted); raises `MockServiceError` with appropriate code (`rate_limit`, `not_found`, `timeout`, `server_error`)
- Called at the top of every service method

**`slack_service.py` — `SlackService`**
- `send_message(channel, text, user)` — validates channel exists; appends to message list; returns `{ok, ts, channel}`
- `list_channels()` — returns channel list
- `search_messages(query, channel?)` — case-insensitive substring search across stored messages

**`calendar_service.py` — `CalendarService`**
- `create_event(title, start, end, attendees, description?)` — validates ISO datetimes; detects overlap; returns event with generated `id`
- `list_events(start, end)` — events whose range intersects `[start, end]`
- `find_free_slot(duration_minutes, after, before)` — walks existing events in range; returns first gap ≥ duration

**`jira_service.py` — `JiraService`**
- `create_issue(summary, description?, assignee?, priority?)` — generates `PRJ-{n}` key; status defaults to `"To Do"`
- `get_issue(key)` — returns issue or raises `not_found`
- `transition_issue(key, status, assignee?)` — validates allowed transitions (`To Do → In Progress → Done`); optionally updates assignee

**`email_service.py` — `EmailService`**
- `send_email(to, subject, body, cc?)` — stores in outbox with timestamp + generated `id`
- `search_email(query, folder?)` — searches `inbox` or `outbox` (or both); substring match on subject + body

### 7. `src/cli/interface.py`
- `AgentCLI(settings)` — creates services, registry, and loop internally; no background threads
- REPL: `rich` prompt → `loop.run(input)` → render each `StepEvent`:
  - `reasoning` → `[dim italic]`
  - `tool_call` → `[cyan]` panel with name + pretty-printed args
  - `tool_result` → `[green]` or `[red]` (error)
  - final answer → `[bold white]` panel
- After each query: print a **summary of actions taken** (list of tool calls executed and their outcomes)
- `ctrl+c` / `quit` / `exit` → clean shutdown

---

## Implementation Steps (ordered)

| # | Step | Files |
|---|---|---|
| 1 | Project scaffold | `pyproject.toml`, `.env.example`, `.gitignore`, package `__init__.py` stubs |
| 2 | Config | `src/agent/config.py` |
| 3 | Persistence + error injector | `src/mock_services/persistence.py`, `src/mock_services/base.py` |
| 4 | Mock service — Slack | `src/mock_services/slack_service.py` + seed `data/slack.json` |
| 5 | Mock service — Calendar | `src/mock_services/calendar_service.py` + seed `data/calendar.json` |
| 6 | Mock service — Jira | `src/mock_services/jira_service.py` + seed `data/jira.json` |
| 7 | Mock service — Email | `src/mock_services/email_service.py` + seed `data/email.json` |
| 8 | LLM client | `src/agent/llm_client.py` |
| 9 | Tool base + registry | `src/tools/base.py`, `src/tools/registry.py` |
| 10 | Tool implementations | `src/tools/slack.py`, `calendar.py`, `jira.py`, `email.py` |
| 11 | ReAct loop | `src/agent/loop.py` |
| 12 | CLI | `src/cli/interface.py`, `agent.py` |
| 13 | Unit tests | `tests/unit/test_*.py` |
| 14 | Integration tests | `tests/integration/test_scenarios.py` (A–D), `test_mock_services.py` |
| 15 | README + DECISIONS | `README.md`, `DECISIONS.md` |

---

## Environment Variables (`.env.example`)

```
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o

MOCK_ERROR_RATE=0.0          # 0.0–1.0 random failure rate across all services
MOCK_FORCE_ERROR=            # e.g. "slack:rate_limit", "jira:not_found"

LOG_LEVEL=INFO               # DEBUG | INFO | WARNING
LOG_FILE=                    # optional path for file output

MAX_AGENT_STEPS=20
CURRENT_USER=john.doe        # used by Jira "assign to me"
DATA_DIR=data                # directory for JSON state files
```

---

## Scenario D — Ambiguous Prompt Handling

Scenario D (`"Send an update."`) is handled entirely by the system prompt — no special code path needed. The system prompt instructs the LLM to ask for clarification (channel, content, recipients) when the request is underspecified. The loop handles this naturally: the LLM returns a `content`-only response (no `tool_calls`), which the loop surfaces as the final answer. The integration test for Scenario D scripts the LLM to return a clarifying question and asserts no tool calls were made.

---

## Test Strategy

- **Unit tests**: services are instantiated with a `tmp_path` data dir; LLM mocked by replacing `OpenAIClient.chat()` with a fixture returning scripted `LLMResponse` sequences; no HTTP mocking needed
- **Integration tests**: full `agent loop + registry + real services` wired together; LLM responses scripted to drive each scenario A–D; assert correct tool call sequence and non-empty final answer
- **No real API keys** required for any test
- **Coverage target**: ≥80% on `src/` (`pytest-cov --fail-under=80`)
- **Mypy**: `--strict` on `src/`; configured in `pyproject.toml`
- **Run**: `pytest` (entry in `pyproject.toml`)

---

## Verification

1. `cp .env.example .env` → fill in OpenAI key
2. `python agent.py` → run scenarios A–D manually
3. `pytest --cov=src --cov-report=term-missing` → ≥80% coverage
4. `mypy src/` → zero errors
