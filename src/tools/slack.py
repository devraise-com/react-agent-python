"""Slack tool wrappers — thin closures around SlackService."""

from typing import Any

from src.mock_services.slack_service import SlackService
from src.tools.registry import ToolRegistry


def register_slack_tools(service: SlackService, registry: ToolRegistry) -> None:
    """Register all Slack tools into the given registry."""

    @registry.register
    def slack_send_message(channel: str, text: str, user: str = "agent") -> dict[str, Any]:
        """Send a message to a Slack channel.
        Use the channel name with or without the # prefix (e.g. #engineering or engineering).
        """
        return service.send_message(channel, text, user)

    @registry.register
    def slack_list_channels() -> dict[str, Any]:
        """List all available Slack channels in the workspace."""
        return service.list_channels()

    @registry.register
    def slack_search_messages(query: str, channel: str | None = None) -> dict[str, Any]:
        """Search for messages across Slack.
        Optionally filter by channel name (with or without # prefix).
        """
        return service.search_messages(query, channel)
