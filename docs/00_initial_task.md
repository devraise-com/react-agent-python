**Engineering Assignment**

Senior/Lead AI Engineer — AI Agents

| Position level | Senior (5+ years of experience) |
| :---- | :---- |
| **Implementation language** | Python 3.10+ |
| **AI model** | Your choice (Anthropic, OpenAI, Ollama, …) |
| **Delivery format** | Git repository (GitHub / GitLab) |

# **1\. Context and Goal**

We are building an AI-powered workplace automation platform. Imagine a tool that lets an employee type what they want to accomplish — in plain English — and an AI agent selects the right tools, calls the appropriate APIs, and confirms what was done. For example:

| 💬 Example user prompts "Schedule a sprint review with the team tomorrow at 2 PM." "Send a message to \#design saying the Figma mockups are ready for review." "Approve pull request \#42 and close the related Jira ticket." "Find all open tasks assigned to me and send me a summary by email." |
| :---- |

Your task is to design and implement a prototype of such an agent. For practical reasons, external APIs (Slack, Google Calendar, Jira, Figma) will be mocked — implementing those mocks is an intentional and graded part of the assignment.

# **2\. Functional Requirements**

## **2.1 User Interface (CLI)**

The agent must be runnable from the command line and support the below model:

| \# interactive mode python agent.py |
| :---- |

## **2.2 Agent Tools**

The agent must support at least three of the following tool groups. In the scope of the task please set up mock server/servers and use them. Do not connect to real APIs.

| Tool | Actions to implement | Mock API backend |
| :---- | :---- | :---- |
| Slack | send\_message, list\_channels, search\_messages | JSON file / in-memory store |
| Google Calendar | create\_event, list\_events, find\_free\_slot | JSON file / in-memory store |
| Jira / Linear | create\_issue, get\_issue, transition\_issue | JSON file / in-memory store |
| Figma | get\_file\_info, add\_comment, list\_comments | JSON file / in-memory store |
| Email (Gmail) | send\_email, search\_email | JSON file / in-memory store |

## **2.3 Agent Loop**

The agent should implement a ReAct (Reason \+ Act) loop or equivalent. We expect you to build the loop yourself — do not use high-level agent frameworks such as LangChain, LangGraph, CrewAI, or AutoGen. You may use official LLM SDKs (Anthropic, OpenAI, etc.) and helper libraries (pydantic, httpx, rich, …).

| 🔄 Minimum agent loop 1\. Accept the user prompt 2\. Send to LLM with the available tool list (function/tool calling) 3\. If the LLM wants to call a tool — call it and return the result to the LLM 4\. Repeat step 3 until the LLM returns a final answer (or a step limit is reached) 5\. Present the user with a summary of actions taken |
| :---- |

# **3\. Technical Requirements**

## **3.1 Architecture and Code Quality**

* Python 3.10+ with full type hints (mypy or pyright must pass without errors)

* Clear layer separation: LLM client • agent loop • tool registry • mock APIs • CLI

* Configuration via environment variables or a .env file (API key, model selection)

* Error handling: timeouts, retry with backoff, clear user-facing error messages

* Structured logging (logging / structlog) — DEBUG and INFO levels, optional file output

## **3.2 Tests**

* At least 80% unit test coverage for core modules

* Integration tests verifying the full flow: prompt → tool call → response

* Mock the LLM in tests — tests must not require real API keys or internet access

* Run with: pytest, configured in pyproject.toml

## **3.3 Mock API — Detailed Requirements**

The mock API is not a simple hardcoded return. We expect a realistic simulation:

* State is persisted between calls (e.g. messages sent by the agent are visible in a later search)

* Parameter validation — the mock rejects invalid inputs just like the real API would

* Ability to inject errors (rate limit, 404, timeout) via environment variable or config

* Response format consistent with the real API schema (simplified but internally coherent)

## **3.4 Documentation**

* README.md: how to run locally, how to run tests, architecture overview (diagram or ASCII)

* DECISIONS.md: a short file explaining key design decisions and the reasoning behind your choices

* Code comments and docstrings where they add genuine value — not everywhere by default

# **4\. Test Scenarios (verified during the interview)**

During the technical review we will ask you to demo the agent against the scenarios below. The agent should handle them correctly without any hardcoded responses.

## **Scenario A — Simple action**

| Prompt: "Send a message to \#engineering: Deployment of v2.4.1 completed successfully." Expected behaviour:   1\. Agent identifies the tool: slack.send\_message   2\. Calls the mock API with the correct parameters   3\. Confirms the action to the user |
| :---- |

## **Scenario B — Multi-step action**

| Prompt: "Create a Jira ticket for the login bug, assign it to me,          then notify \#backend-team on Slack." Expected behaviour:   1\. jira.create\_issue — create the ticket   2\. jira.transition\_issue or assign — assign to the current user   3\. slack.send\_message — post a notification with the ticket link |
| :---- |

## **Scenario C — Search and aggregation**

| Prompt: "Show me all my calendar events this week          and find a free 2-hour slot for a meeting." Expected behaviour:   1\. calendar.list\_events — fetch this week's events   2\. calendar.find\_free\_slot — analyse and suggest a slot   3\. Agent presents the result in a readable format |
| :---- |

## **Scenario D — Ambiguous prompt (edge case)**

| Prompt: "Send an update." Expected behaviour:   Agent asks for clarification (where, what, when)   — No API keys or external services required to handle this case |
| :---- |

# **5\. Evaluation Criteria**

| Criterion | Weight | What we look for |
| :---- | ----- | :---- |
| **Agent correctness** | **30%** | All scenarios work as expected |
| **Architecture and design** | **25%** | Separation of concerns, extensibility, clean code |
| **Mock API quality** | **20%** | Realism, stateful behaviour, validation, error injection |
| **Tests** | **15%** | Coverage, assertion quality, no external dependencies |
| **Documentation and decisions** | **10%** | DECISIONS.md, clear reasoning behind choices |

# **6\. Things We Are Not Evaluating (but nice to have)**

* A web UI — a CLI is perfectly sufficient

* Multi-user concurrency — single-user is enough

* Docker / infrastructure setup (great if you have time, not required)

* Polished CLI UX — functionality matters more than prompt aesthetics

| 💡 Tip We prefer a well-thought-out, simpler system over a complex but chaotic one. DECISIONS.md is your opportunity to show us how you reason about trade-offs. |
| :---- |

# **7\. Provided Resources**

## **7.1 LLM API Key**

If you choose to use Anthropic Claude or OpenAI, reach out to us — we will provide a temporary API key for the duration of the assignment. You may also use a local model via Ollama (e.g. llama3, mistral) at no cost or any other alternative.

## **7.2 Example Mock API Schemas**

Below is an example schema for the Slack Mock API. Please design the remaining tools yourself. It doesn’t need to be anything sophisticated.

| \# Slack Mock API — example request/response schemas \# POST /slack/send\_message \# Request: { "channel": "\#engineering", "text": "Hello world", "user": "bot" } \# Response: { "ok": true, "ts": "1714000000.123456", "channel": "C01234567" } \# GET /slack/channels \# Response: { "ok": true, "channels": \[     { "id": "C01234567", "name": "engineering", "is\_member": true }   \] } \# GET /slack/search?query=deploy \# Response: { "ok": true, "messages": \[     { "ts": "...", "text": "Deploy v2.4.1", "user": "bot", "channel": "\#engineering" }   \] } |
| :---- |

# **8\. Delivery**

* Public or private Git repository (with recruiter access) on GitHub or GitLab

* README.md at the repository root with setup and run instructions

* DECISIONS.md with key architectural decisions and your reasoning

| ⚠️  Important Do not commit your API key to the repository. Use a .env file with .gitignore. Include a .env.example file describing all required environment variables. |
| :---- |

# **9\. Questions**

If you have any questions about the assignment, feel free to reach out. Questions are welcome — they are part of the process, not a weakness.

**Good luck\!**

We look forward to your repository — not a perfect one, but a thoughtful one.