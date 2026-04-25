# ReAct AI Agent

A CLI-based AI agent for workplace automation built with a hand-rolled ReAct (Reason + Act) loop, OpenAI GPT-4o, and mock services for Slack, Google Calendar, Jira, and Email.

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
│  ├ slack.py      │  ├ calendar.py                    │  thin closures
│  ├ jira.py       │  └ email.py                       │
├──────────────────┴──────────────────────────────────┤
│  Mock Services  (src/mock_services/)                 │  in-process, stateful
│  SlackService · CalendarService · JiraService        │  Pydantic validation
│  EmailService · JsonStore · ErrorInjector            │  JSON persistence, error inject
└─────────────────────────────────────────────────────┘
```

## Setup

**Requirements:** Python 3.10+

```bash
# 1. Clone and enter the repo
git clone <repo-url>
cd react-agent-python

# 2. Create a virtual environment
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -e ".[dev]"

# 4. Configure environment
cp .env.example .env
# Edit .env and set OPENAI_API_KEY=sk-...
```

## Running the Agent

```bash
python agent.py
```

The agent starts an interactive REPL. Type your request in plain English:

```
You: Send a message to #engineering: Deployment of v2.4.1 completed successfully.
You: Create a Jira ticket for the login bug, assign it to me, then notify #backend-team.
You: Show me all my calendar events this week and find a free 2-hour slot.
You: Send an update.       # agent will ask for clarification
You: quit
```

## Running Tests

```bash
# Run all tests with coverage report
pytest --cov=src --cov-report=term-missing

# Run only unit tests
pytest tests/unit/

# Run only integration tests
pytest tests/integration/
```

No real API keys are required to run the tests — the LLM is mocked via scripted responses.

## Mock Service Error Injection

Control error behaviour via environment variables for testing / demo:

```bash
# 10% random failure rate on all service calls
MOCK_ERROR_RATE=0.1 python agent.py

# Force Slack to return a rate-limit error on the next call
MOCK_FORCE_ERROR=slack:rate_limit python agent.py

# Available error codes: rate_limit | not_found | timeout | server_error
# Available services:    slack | calendar | jira | email
```

## Type Checking

```bash
mypy src/
```

## Project Structure

```
react-agent-python/
├── agent.py                  # CLI entry point
├── pyproject.toml            # deps, pytest, mypy, coverage
├── .env.example              # environment variable template
├── docs/                     # assignment and implementation plan
├── src/
│   ├── agent/                # config, llm_client, loop
│   ├── tools/                # registry + 4 tool modules
│   ├── mock_services/        # 4 stateful mock services + persistence
│   └── cli/                  # rich REPL
├── tests/
│   ├── unit/                 # per-module unit tests
│   └── integration/          # scenario A–D + service contract tests
└── data/                     # runtime JSON state (git-ignored)
```
