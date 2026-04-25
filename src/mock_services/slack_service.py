"""Mock Slack service — stateful in-process simulation."""

import time
from typing import Any

from src.mock_services.base import ErrorCode, ErrorInjector, MockServiceError
from src.mock_services.persistence import JsonStore

SLACK_DEFAULTS: dict[str, Any] = {
    "channels": [
        {"id": "C001", "name": "engineering", "is_member": True},
        {"id": "C002", "name": "design", "is_member": True},
        {"id": "C003", "name": "backend-team", "is_member": True},
        {"id": "C004", "name": "general", "is_member": True},
        {"id": "C005", "name": "random", "is_member": False},
    ],
    "messages": {},
}


class SlackService:
    """Simulates Slack workspace API with persistent state."""

    def __init__(self, store: JsonStore, injector: ErrorInjector) -> None:
        self._store = store
        self._injector = injector

    def send_message(
        self, channel: str, text: str, user: str = "agent"
    ) -> dict[str, Any]:
        """Send a message to a channel. Returns {ok, ts, channel_id}."""
        self._injector.maybe_raise("slack")

        channel = channel.lstrip("#")
        if not text.strip():
            raise MockServiceError(ErrorCode.SERVER_ERROR, "text must not be empty")

        data = self._store.read()
        channel_obj = next(
            (c for c in data["channels"] if c["name"] == channel), None
        )
        if channel_obj is None:
            raise MockServiceError(
                ErrorCode.NOT_FOUND, f"Channel #{channel} not found"
            )

        ts = f"{time.time():.6f}"
        message: dict[str, Any] = {
            "ts": ts,
            "text": text,
            "user": user,
            "channel": f"#{channel}",
        }

        def _append(d: dict[str, Any]) -> dict[str, Any]:
            d["messages"].setdefault(channel, []).append(message)
            return d

        self._store.update(_append)
        return {"ok": True, "ts": ts, "channel": channel_obj["id"]}

    def list_channels(self) -> dict[str, Any]:
        """Return all channels in the workspace."""
        self._injector.maybe_raise("slack")
        data = self._store.read()
        return {"ok": True, "channels": data["channels"]}

    def search_messages(
        self, query: str, channel: str | None = None
    ) -> dict[str, Any]:
        """Case-insensitive substring search across stored messages."""
        self._injector.maybe_raise("slack")

        data = self._store.read()
        query_lower = query.lower()
        results: list[dict[str, Any]] = []

        for ch_name, messages in data["messages"].items():
            if channel and ch_name != channel.lstrip("#"):
                continue
            for msg in messages:
                if query_lower in msg["text"].lower():
                    results.append(msg)

        return {"ok": True, "messages": results}
