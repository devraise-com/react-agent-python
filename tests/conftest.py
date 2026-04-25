"""Shared fixtures for all tests."""

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from src.agent.config import Settings
from src.agent.llm_client import LLMClient, LLMResponse, ToolCall
from src.mock_services.base import ErrorInjector
from src.mock_services.calendar_service import CALENDAR_DEFAULTS, CalendarService
from src.mock_services.email_service import EMAIL_DEFAULTS, EmailService
from src.mock_services.jira_service import JIRA_DEFAULTS, JiraService
from src.mock_services.persistence import JsonStore
from src.mock_services.slack_service import SLACK_DEFAULTS, SlackService
from src.tools.calendar import register_calendar_tools
from src.tools.email import register_email_tools
from src.tools.jira import register_jira_tools
from src.tools.registry import ToolRegistry
from src.tools.slack import register_slack_tools


# ---------------------------------------------------------------------------
# Mock LLM client
# ---------------------------------------------------------------------------


class ScriptedLLMClient(LLMClient):
    """Returns pre-scripted LLMResponse objects in sequence."""

    def __init__(self, responses: list[LLMResponse]) -> None:
        self._responses = iter(responses)

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> LLMResponse:
        return next(self._responses)


# ---------------------------------------------------------------------------
# Settings / injector fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_settings(tmp_path: Path) -> Settings:
    return Settings(
        openai_api_key="test-key",
        openai_model="gpt-4o",
        data_dir=tmp_path,
        max_agent_steps=10,
    )


@pytest.fixture
def no_errors() -> ErrorInjector:
    return ErrorInjector(error_rate=0.0, force_error="")


# ---------------------------------------------------------------------------
# Service fixtures (isolated per-test via tmp_path)
# ---------------------------------------------------------------------------


@pytest.fixture
def slack_service(tmp_path: Path, no_errors: ErrorInjector) -> SlackService:
    store = JsonStore(tmp_path / "slack.json", SLACK_DEFAULTS)
    return SlackService(store, no_errors)


@pytest.fixture
def calendar_service(tmp_path: Path, no_errors: ErrorInjector) -> CalendarService:
    store = JsonStore(tmp_path / "calendar.json", CALENDAR_DEFAULTS)
    return CalendarService(store, no_errors)


@pytest.fixture
def jira_service(tmp_path: Path, no_errors: ErrorInjector) -> JiraService:
    store = JsonStore(tmp_path / "jira.json", JIRA_DEFAULTS)
    return JiraService(store, no_errors)


@pytest.fixture
def email_service(tmp_path: Path, no_errors: ErrorInjector) -> EmailService:
    store = JsonStore(tmp_path / "email.json", EMAIL_DEFAULTS)
    return EmailService(store, no_errors)


# ---------------------------------------------------------------------------
# Registry fixture (fully wired with real services)
# ---------------------------------------------------------------------------


@pytest.fixture
def full_registry(
    slack_service: SlackService,
    calendar_service: CalendarService,
    jira_service: JiraService,
    email_service: EmailService,
) -> ToolRegistry:
    registry = ToolRegistry()
    register_slack_tools(slack_service, registry)
    register_calendar_tools(calendar_service, registry)
    register_jira_tools(jira_service, registry)
    register_email_tools(email_service, registry)
    return registry
