"""Google Calendar tool wrappers — thin closures around CalendarService."""

from typing import Any

from src.mock_services.calendar_service import CalendarService
from src.tools.registry import ToolRegistry


def register_calendar_tools(service: CalendarService, registry: ToolRegistry) -> None:
    """Register all Calendar tools into the given registry."""

    @registry.register
    def calendar_create_event(
        title: str,
        start: str,
        end: str,
        attendees: list[str],
        description: str = "",
    ) -> dict[str, Any]:
        """Create a Google Calendar event.
        start and end must be ISO 8601 datetime strings (e.g. 2026-04-28T14:00:00).
        attendees is a list of email addresses.
        """
        return service.create_event(title, start, end, attendees, description)

    @registry.register
    def calendar_list_events(start: str, end: str) -> dict[str, Any]:
        """List calendar events within a time range.
        start and end must be ISO 8601 datetime strings.
        """
        return service.list_events(start, end)

    @registry.register
    def calendar_find_free_slot(
        duration_minutes: int, after: str, before: str
    ) -> dict[str, Any]:
        """Find the first free time slot of the given duration.
        after and before must be ISO 8601 datetime strings defining the search window.
        """
        return service.find_free_slot(duration_minutes, after, before)
