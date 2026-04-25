"""Mock Google Calendar service — stateful in-process simulation."""

from datetime import datetime, timedelta
from typing import Any

from src.mock_services.base import ErrorCode, ErrorInjector, MockServiceError
from src.mock_services.persistence import JsonStore

CALENDAR_DEFAULTS: dict[str, Any] = {
    "events": [
        {
            "id": "EVT-0001",
            "title": "Team standup",
            "start": "2026-04-28T09:00:00",
            "end": "2026-04-28T09:30:00",
            "attendees": ["team@company.com"],
            "description": "Daily standup",
        },
        {
            "id": "EVT-0002",
            "title": "Sprint planning",
            "start": "2026-04-28T14:00:00",
            "end": "2026-04-28T16:00:00",
            "attendees": ["team@company.com", "pm@company.com"],
            "description": "Sprint 24 planning",
        },
    ]
}


def _parse_dt(value: str, field: str) -> datetime:
    try:
        return datetime.fromisoformat(value)
    except ValueError as exc:
        raise MockServiceError(
            ErrorCode.SERVER_ERROR, f"Invalid ISO datetime for '{field}': {value}"
        ) from exc


class CalendarService:
    """Simulates Google Calendar API with persistent state."""

    def __init__(self, store: JsonStore, injector: ErrorInjector) -> None:
        self._store = store
        self._injector = injector

    def create_event(
        self,
        title: str,
        start: str,
        end: str,
        attendees: list[str],
        description: str = "",
    ) -> dict[str, Any]:
        """Create a calendar event. start/end must be ISO 8601 strings."""
        self._injector.maybe_raise("calendar")

        start_dt = _parse_dt(start, "start")
        end_dt = _parse_dt(end, "end")

        if end_dt <= start_dt:
            raise MockServiceError(
                ErrorCode.SERVER_ERROR, "'end' must be after 'start'"
            )

        def _add(d: dict[str, Any]) -> dict[str, Any]:
            event_id = f"EVT-{len(d['events']) + 1:04d}"
            d["events"].append(
                {
                    "id": event_id,
                    "title": title,
                    "start": start,
                    "end": end,
                    "attendees": attendees,
                    "description": description,
                }
            )
            return d

        updated = self._store.update(_add)
        return {"ok": True, "event": updated["events"][-1]}

    def list_events(self, start: str, end: str) -> dict[str, Any]:
        """Return events whose range intersects [start, end]."""
        self._injector.maybe_raise("calendar")

        start_dt = _parse_dt(start, "start")
        end_dt = _parse_dt(end, "end")

        data = self._store.read()
        results = [
            e
            for e in data["events"]
            if _parse_dt(e["start"], "start") < end_dt
            and _parse_dt(e["end"], "end") > start_dt
        ]
        return {"ok": True, "events": results}

    def find_free_slot(
        self, duration_minutes: int, after: str, before: str
    ) -> dict[str, Any]:
        """Find the first free slot of `duration_minutes` within [after, before]."""
        self._injector.maybe_raise("calendar")

        after_dt = _parse_dt(after, "after")
        before_dt = _parse_dt(before, "before")
        duration = timedelta(minutes=duration_minutes)

        events = self.list_events(after, before)["events"]
        events_sorted = sorted(events, key=lambda e: e["start"])

        candidate = after_dt
        for event in events_sorted:
            event_start = _parse_dt(event["start"], "start")
            if candidate + duration <= event_start:
                return {
                    "ok": True,
                    "slot": {
                        "start": candidate.isoformat(),
                        "end": (candidate + duration).isoformat(),
                    },
                }
            event_end = _parse_dt(event["end"], "end")
            if event_end > candidate:
                candidate = event_end

        if candidate + duration <= before_dt:
            return {
                "ok": True,
                "slot": {
                    "start": candidate.isoformat(),
                    "end": (candidate + duration).isoformat(),
                },
            }

        return {"ok": False, "slot": None, "message": "No free slot found in range"}
