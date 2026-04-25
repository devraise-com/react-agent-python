"""Mock Email (Gmail) service — stateful in-process simulation."""

from datetime import datetime, timezone
from typing import Any

from src.mock_services.base import ErrorCode, ErrorInjector, MockServiceError
from src.mock_services.persistence import JsonStore

EMAIL_DEFAULTS: dict[str, Any] = {
    "inbox": [
        {
            "id": "MSG-001",
            "from": "manager@company.com",
            "to": ["john.doe@company.com"],
            "cc": [],
            "subject": "Sprint review preparation",
            "body": (
                "Please prepare slides for Friday's sprint review meeting. "
                "Focus on key achievements and blockers."
            ),
            "timestamp": "2026-04-24T09:00:00",
        },
        {
            "id": "MSG-002",
            "from": "teammate@company.com",
            "to": ["john.doe@company.com"],
            "cc": [],
            "subject": "PR review request",
            "body": (
                "Hey, could you review my PR for the authentication module? "
                "Link: github.com/company/repo/pull/42"
            ),
            "timestamp": "2026-04-24T11:30:00",
        },
    ],
    "outbox": [],
}

VALID_FOLDERS = {"inbox", "outbox", "all"}


class EmailService:
    """Simulates Gmail API with persistent state."""

    def __init__(self, store: JsonStore, injector: ErrorInjector) -> None:
        self._store = store
        self._injector = injector

    def send_email(
        self,
        to: list[str],
        subject: str,
        body: str,
        cc: list[str] | None = None,
    ) -> dict[str, Any]:
        """Send an email; stores it in outbox. Returns {ok, id, timestamp}."""
        self._injector.maybe_raise("email")

        if not to:
            raise MockServiceError(ErrorCode.SERVER_ERROR, "'to' must not be empty")
        if not subject.strip():
            raise MockServiceError(ErrorCode.SERVER_ERROR, "'subject' must not be empty")

        def _add(d: dict[str, Any]) -> dict[str, Any]:
            total = len(d["inbox"]) + len(d["outbox"])
            email: dict[str, Any] = {
                "id": f"MSG-{total + 1:03d}",
                "to": to,
                "cc": cc or [],
                "subject": subject,
                "body": body,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            d["outbox"].append(email)
            return d

        updated = self._store.update(_add)
        sent = updated["outbox"][-1]
        return {"ok": True, "id": sent["id"], "timestamp": sent["timestamp"]}

    def search_email(
        self, query: str, folder: str = "inbox"
    ) -> dict[str, Any]:
        """Substring search on subject + body. folder: inbox | outbox | all."""
        self._injector.maybe_raise("email")

        if folder not in VALID_FOLDERS:
            raise MockServiceError(
                ErrorCode.SERVER_ERROR,
                f"Invalid folder '{folder}'. Must be one of: {sorted(VALID_FOLDERS)}",
            )

        data = self._store.read()
        query_lower = query.lower()
        sources: list[dict[str, Any]] = []

        if folder in ("inbox", "all"):
            sources.extend(data.get("inbox", []))
        if folder in ("outbox", "all"):
            sources.extend(data.get("outbox", []))

        results = [
            e
            for e in sources
            if query_lower in e["subject"].lower() or query_lower in e["body"].lower()
        ]
        return {"ok": True, "messages": results}
