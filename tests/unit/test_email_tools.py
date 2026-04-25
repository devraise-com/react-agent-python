"""Unit tests for Email tool wrappers."""

import pytest

from src.mock_services.email_service import EmailService
from src.tools.base import ToolError
from src.tools.email import register_email_tools
from src.tools.registry import ToolRegistry


@pytest.fixture
def registry(email_service: EmailService) -> ToolRegistry:
    r = ToolRegistry()
    register_email_tools(email_service, r)
    return r


def test_send_email_success(registry: ToolRegistry) -> None:
    result = registry.dispatch(
        "email_send",
        {
            "to": ["alice@company.com"],
            "subject": "Hello",
            "body": "Hi Alice!",
        },
    )
    assert result["ok"] is True
    assert result["id"].startswith("MSG-")
    assert "timestamp" in result


def test_send_email_with_cc(registry: ToolRegistry) -> None:
    result = registry.dispatch(
        "email_send",
        {
            "to": ["alice@company.com"],
            "subject": "CC test",
            "body": "body",
            "cc": ["bob@company.com"],
        },
    )
    assert result["ok"] is True


def test_send_email_empty_to_raises(registry: ToolRegistry) -> None:
    with pytest.raises(ToolError, match="'to'"):
        registry.dispatch(
            "email_send",
            {"to": [], "subject": "Empty", "body": "body"},
        )


def test_send_email_empty_subject_raises(registry: ToolRegistry) -> None:
    with pytest.raises(ToolError, match="subject"):
        registry.dispatch(
            "email_send",
            {"to": ["alice@company.com"], "subject": "  ", "body": "body"},
        )


def test_search_inbox_finds_seed_message(registry: ToolRegistry) -> None:
    result = registry.dispatch("email_search", {"query": "sprint review"})
    assert result["ok"] is True
    assert len(result["messages"]) >= 1


def test_search_outbox_empty_initially(registry: ToolRegistry) -> None:
    result = registry.dispatch("email_search", {"query": "hello", "folder": "outbox"})
    assert result["messages"] == []


def test_search_finds_sent_message(registry: ToolRegistry) -> None:
    registry.dispatch(
        "email_send",
        {"to": ["bob@company.com"], "subject": "Deploy complete", "body": "v2.4.1 done"},
    )
    result = registry.dispatch(
        "email_search", {"query": "deploy complete", "folder": "outbox"}
    )
    assert len(result["messages"]) == 1


def test_search_invalid_folder_raises(registry: ToolRegistry) -> None:
    with pytest.raises(ToolError, match="folder"):
        registry.dispatch("email_search", {"query": "x", "folder": "spam"})


def test_search_all_folders(registry: ToolRegistry) -> None:
    registry.dispatch(
        "email_send",
        {"to": ["x@y.com"], "subject": "Unique subject xyz", "body": "body"},
    )
    result = registry.dispatch(
        "email_search", {"query": "Unique subject xyz", "folder": "all"}
    )
    assert len(result["messages"]) == 1
