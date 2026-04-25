"""Unit tests for Jira tool wrappers."""

import pytest

from src.mock_services.jira_service import JiraService
from src.tools.base import ToolError
from src.tools.jira import register_jira_tools
from src.tools.registry import ToolRegistry


@pytest.fixture
def registry(jira_service: JiraService) -> ToolRegistry:
    r = ToolRegistry()
    register_jira_tools(jira_service, r)
    return r


def test_create_issue_success(registry: ToolRegistry) -> None:
    result = registry.dispatch(
        "jira_create_issue",
        {"summary": "Login page broken", "description": "500 error on login"},
    )
    assert result["ok"] is True
    issue = result["issue"]
    assert issue["key"].startswith("PRJ-")
    assert issue["status"] == "To Do"
    assert issue["priority"] == "Medium"


def test_create_issue_assigns_user(registry: ToolRegistry) -> None:
    result = registry.dispatch(
        "jira_create_issue",
        {"summary": "Bug", "assignee": "john.doe", "priority": "High"},
    )
    assert result["issue"]["assignee"] == "john.doe"


def test_create_issue_invalid_priority_raises(registry: ToolRegistry) -> None:
    with pytest.raises(ToolError, match="priority"):
        registry.dispatch("jira_create_issue", {"summary": "X", "priority": "URGENT"})


def test_create_issue_empty_summary_raises(registry: ToolRegistry) -> None:
    with pytest.raises(ToolError, match="summary"):
        registry.dispatch("jira_create_issue", {"summary": "  "})


def test_get_issue_existing(registry: ToolRegistry) -> None:
    # PRJ-1 is in seed data
    result = registry.dispatch("jira_get_issue", {"key": "PRJ-1"})
    assert result["ok"] is True
    assert result["issue"]["key"] == "PRJ-1"


def test_get_issue_not_found_raises(registry: ToolRegistry) -> None:
    with pytest.raises(ToolError, match="not found"):
        registry.dispatch("jira_get_issue", {"key": "PRJ-999"})


def test_transition_issue_valid(registry: ToolRegistry) -> None:
    # PRJ-1 is "In Progress" in seed → can go to "Done"
    result = registry.dispatch(
        "jira_transition_issue", {"key": "PRJ-1", "status": "Done"}
    )
    assert result["ok"] is True
    assert result["issue"]["status"] == "Done"


def test_transition_issue_invalid_raises(registry: ToolRegistry) -> None:
    # PRJ-1 is "In Progress" → cannot go directly to "To Do"... wait, TRANSITIONS says it can
    # Let's try an invalid transition: "To Do" → "Done" (not allowed)
    # First create an issue (status="To Do"), then try to go to "Done"
    created = registry.dispatch("jira_create_issue", {"summary": "New issue"})
    key = created["issue"]["key"]
    with pytest.raises(ToolError, match="Cannot transition"):
        registry.dispatch("jira_transition_issue", {"key": key, "status": "Done"})


def test_transition_updates_assignee(registry: ToolRegistry) -> None:
    result = registry.dispatch(
        "jira_transition_issue",
        {"key": "PRJ-1", "status": "Done", "assignee": "jane.doe"},
    )
    assert result["issue"]["assignee"] == "jane.doe"
