"""Unit tests for Calendar tool wrappers."""

import pytest

from src.mock_services.calendar_service import CalendarService
from src.tools.base import ToolError
from src.tools.calendar import register_calendar_tools
from src.tools.registry import ToolRegistry


@pytest.fixture
def registry(calendar_service: CalendarService) -> ToolRegistry:
    r = ToolRegistry()
    register_calendar_tools(calendar_service, r)
    return r


def test_create_event_success(registry: ToolRegistry) -> None:
    result = registry.dispatch(
        "calendar_create_event",
        {
            "title": "Sprint review",
            "start": "2026-04-30T10:00:00",
            "end": "2026-04-30T11:00:00",
            "attendees": ["team@company.com"],
        },
    )
    assert result["ok"] is True
    assert result["event"]["title"] == "Sprint review"
    assert result["event"]["id"].startswith("EVT-")


def test_create_event_end_before_start_raises(registry: ToolRegistry) -> None:
    with pytest.raises(ToolError, match="end.*after.*start|start.*end"):
        registry.dispatch(
            "calendar_create_event",
            {
                "title": "Bad event",
                "start": "2026-04-30T11:00:00",
                "end": "2026-04-30T10:00:00",
                "attendees": [],
            },
        )


def test_create_event_invalid_datetime_raises(registry: ToolRegistry) -> None:
    with pytest.raises(ToolError):
        registry.dispatch(
            "calendar_create_event",
            {
                "title": "Bad",
                "start": "not-a-date",
                "end": "2026-04-30T11:00:00",
                "attendees": [],
            },
        )


def test_list_events_in_range(registry: ToolRegistry) -> None:
    # Seed data has events on 2026-04-28
    result = registry.dispatch(
        "calendar_list_events",
        {"start": "2026-04-28T00:00:00", "end": "2026-04-29T00:00:00"},
    )
    assert result["ok"] is True
    assert len(result["events"]) == 2  # standup + sprint planning from seed


def test_list_events_outside_range_empty(registry: ToolRegistry) -> None:
    result = registry.dispatch(
        "calendar_list_events",
        {"start": "2026-05-01T00:00:00", "end": "2026-05-02T00:00:00"},
    )
    assert result["events"] == []


def test_find_free_slot_found(registry: ToolRegistry) -> None:
    # Seed: 09:00–09:30 standup, 14:00–16:00 sprint planning on 2026-04-28
    # A 60-min slot should be found at 09:30
    result = registry.dispatch(
        "calendar_find_free_slot",
        {
            "duration_minutes": 60,
            "after": "2026-04-28T09:00:00",
            "before": "2026-04-28T18:00:00",
        },
    )
    assert result["ok"] is True
    assert result["slot"] is not None
    assert result["slot"]["start"] == "2026-04-28T09:30:00"


def test_find_free_slot_no_slot(registry: ToolRegistry) -> None:
    # Request longer than available gap
    result = registry.dispatch(
        "calendar_find_free_slot",
        {
            "duration_minutes": 999,
            "after": "2026-04-28T09:00:00",
            "before": "2026-04-28T10:00:00",
        },
    )
    assert result["ok"] is False
    assert result["slot"] is None
