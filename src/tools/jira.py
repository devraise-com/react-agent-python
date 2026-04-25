"""Jira tool wrappers — thin closures around JiraService."""

from typing import Any

from src.mock_services.jira_service import JiraService
from src.tools.registry import ToolRegistry


def register_jira_tools(service: JiraService, registry: ToolRegistry) -> None:
    """Register all Jira tools into the given registry."""

    @registry.register
    def jira_create_issue(
        summary: str,
        description: str = "",
        assignee: str = "",
        priority: str = "Medium",
    ) -> dict[str, Any]:
        """Create a new Jira issue.
        priority must be one of: Low, Medium, High, Critical.
        assignee is a username (e.g. john.doe). Leave empty to leave unassigned.
        Returns the created issue with its auto-generated key (e.g. PRJ-5).
        """
        return service.create_issue(summary, description, assignee, priority)

    @registry.register
    def jira_get_issue(key: str) -> dict[str, Any]:
        """Fetch a Jira issue by its key (e.g. PRJ-1)."""
        return service.get_issue(key)

    @registry.register
    def jira_transition_issue(
        key: str, status: str, assignee: str | None = None
    ) -> dict[str, Any]:
        """Change the status of a Jira issue. Optionally update the assignee.
        Allowed transitions: 'To Do' → 'In Progress' → 'Done'.
        """
        return service.transition_issue(key, status, assignee)
