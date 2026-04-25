"""Unit tests for Slack tool wrappers."""

import pytest

from src.mock_services.base import ErrorCode, MockServiceError
from src.mock_services.slack_service import SlackService
from src.tools.registry import ToolRegistry
from src.tools.slack import register_slack_tools


@pytest.fixture
def registry(slack_service: SlackService) -> ToolRegistry:
    r = ToolRegistry()
    register_slack_tools(slack_service, r)
    return r


def test_send_message_success(registry: ToolRegistry) -> None:
    result = registry.dispatch(
        "slack_send_message",
        {"channel": "#engineering", "text": "Hello team!"},
    )
    assert result["ok"] is True
    assert "ts" in result


def test_send_message_channel_without_hash(registry: ToolRegistry) -> None:
    result = registry.dispatch(
        "slack_send_message",
        {"channel": "engineering", "text": "No hash prefix"},
    )
    assert result["ok"] is True


def test_send_message_unknown_channel_raises(registry: ToolRegistry) -> None:
    from src.tools.base import ToolError

    with pytest.raises(ToolError, match="not found"):
        registry.dispatch(
            "slack_send_message",
            {"channel": "#nonexistent", "text": "hi"},
        )


def test_list_channels_returns_all(registry: ToolRegistry) -> None:
    result = registry.dispatch("slack_list_channels", {})
    assert result["ok"] is True
    assert len(result["channels"]) >= 4


def test_search_messages_empty_initially(registry: ToolRegistry) -> None:
    result = registry.dispatch("slack_search_messages", {"query": "deploy"})
    assert result["ok"] is True
    assert result["messages"] == []


def test_search_finds_sent_message(registry: ToolRegistry) -> None:
    registry.dispatch(
        "slack_send_message",
        {"channel": "#engineering", "text": "Deployment v2.4.1 done"},
    )
    result = registry.dispatch("slack_search_messages", {"query": "deployment"})
    assert len(result["messages"]) == 1
    assert "v2.4.1" in result["messages"][0]["text"]


def test_search_filtered_by_channel(registry: ToolRegistry) -> None:
    registry.dispatch("slack_send_message", {"channel": "#engineering", "text": "eng msg"})
    registry.dispatch("slack_send_message", {"channel": "#design", "text": "eng msg also"})

    result = registry.dispatch(
        "slack_search_messages", {"query": "eng msg", "channel": "#design"}
    )
    assert len(result["messages"]) == 1
    assert result["messages"][0]["channel"] == "#design"
