"""Mock Jira service — stateful in-process simulation."""

from datetime import datetime, timezone
from typing import Any

from src.mock_services.base import ErrorCode, ErrorInjector, MockServiceError
from src.mock_services.persistence import JsonStore

JIRA_DEFAULTS: dict[str, Any] = {
    "issues": [
        {
            "key": "PRJ-1",
            "summary": "Setup CI/CD pipeline",
            "description": "Configure GitHub Actions for automated testing and deployment",
            "assignee": "john.doe",
            "priority": "High",
            "status": "In Progress",
            "created": "2026-04-20T10:00:00",
        }
    ],
    "counter": 1,
}

VALID_PRIORITIES = {"Low", "Medium", "High", "Critical"}

# Allowed status transitions
TRANSITIONS: dict[str, list[str]] = {
    "To Do": ["In Progress"],
    "In Progress": ["To Do", "Done"],
    "Done": ["In Progress"],
}


class JiraService:
    """Simulates Jira project management API with persistent state."""

    def __init__(self, store: JsonStore, injector: ErrorInjector) -> None:
        self._store = store
        self._injector = injector

    def create_issue(
        self,
        summary: str,
        description: str = "",
        assignee: str = "",
        priority: str = "Medium",
    ) -> dict[str, Any]:
        """Create a new issue. Returns the created issue with auto-generated key."""
        self._injector.maybe_raise("jira")

        if not summary.strip():
            raise MockServiceError(ErrorCode.SERVER_ERROR, "'summary' must not be empty")
        if priority not in VALID_PRIORITIES:
            raise MockServiceError(
                ErrorCode.SERVER_ERROR,
                f"Invalid priority '{priority}'. Must be one of: {sorted(VALID_PRIORITIES)}",
            )

        def _add(d: dict[str, Any]) -> dict[str, Any]:
            d["counter"] += 1
            d["issues"].append(
                {
                    "key": f"PRJ-{d['counter']}",
                    "summary": summary,
                    "description": description,
                    "assignee": assignee,
                    "priority": priority,
                    "status": "To Do",
                    "created": datetime.now(timezone.utc).isoformat(),
                }
            )
            return d

        updated = self._store.update(_add)
        return {"ok": True, "issue": updated["issues"][-1]}

    def get_issue(self, key: str) -> dict[str, Any]:
        """Fetch an issue by key (e.g. PRJ-1). Raises not_found if missing."""
        self._injector.maybe_raise("jira")

        data = self._store.read()
        issue = next((i for i in data["issues"] if i["key"] == key), None)
        if issue is None:
            raise MockServiceError(ErrorCode.NOT_FOUND, f"Issue {key} not found")
        return {"ok": True, "issue": issue}

    def transition_issue(
        self, key: str, status: str, assignee: str | None = None
    ) -> dict[str, Any]:
        """Change issue status; optionally update assignee."""
        self._injector.maybe_raise("jira")

        data = self._store.read()
        issue = next((i for i in data["issues"] if i["key"] == key), None)
        if issue is None:
            raise MockServiceError(ErrorCode.NOT_FOUND, f"Issue {key} not found")

        current = issue["status"]
        allowed = TRANSITIONS.get(current, [])
        if status not in allowed:
            raise MockServiceError(
                ErrorCode.SERVER_ERROR,
                f"Cannot transition '{key}' from '{current}' to '{status}'. "
                f"Allowed: {allowed}",
            )

        def _update(d: dict[str, Any]) -> dict[str, Any]:
            for i in d["issues"]:
                if i["key"] == key:
                    i["status"] = status
                    if assignee is not None:
                        i["assignee"] = assignee
            return d

        updated = self._store.update(_update)
        updated_issue = next(i for i in updated["issues"] if i["key"] == key)
        return {"ok": True, "issue": updated_issue}
