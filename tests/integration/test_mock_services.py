"""Integration tests for mock services: state persistence, validation, error injection."""

from pathlib import Path

import pytest

from src.mock_services.base import ErrorCode, ErrorInjector, MockServiceError
from src.mock_services.calendar_service import CALENDAR_DEFAULTS, CalendarService
from src.mock_services.email_service import EMAIL_DEFAULTS, EmailService
from src.mock_services.jira_service import JIRA_DEFAULTS, JiraService
from src.mock_services.persistence import JsonStore
from src.mock_services.slack_service import SLACK_DEFAULTS, SlackService


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def test_json_store_seeds_file_on_first_create(tmp_path: Path) -> None:
    path = tmp_path / "test.json"
    assert not path.exists()
    JsonStore(path, {"key": "value"})
    assert path.exists()


def test_json_store_update_persists(tmp_path: Path) -> None:
    store = JsonStore(tmp_path / "data.json", {"count": 0})
    store.update(lambda d: {**d, "count": d["count"] + 1})
    store2 = JsonStore(tmp_path / "data.json", {})
    assert store2.read()["count"] == 1


def test_json_store_reads_existing_file(tmp_path: Path) -> None:
    path = tmp_path / "existing.json"
    path.write_text('{"hello": "world"}', encoding="utf-8")
    store = JsonStore(path, {"hello": "default"})
    assert store.read()["hello"] == "world"


# ---------------------------------------------------------------------------
# Slack: state persistence between calls
# ---------------------------------------------------------------------------


def test_slack_message_persists(tmp_path: Path) -> None:
    inj = ErrorInjector(0.0, "")
    svc = SlackService(JsonStore(tmp_path / "s.json", SLACK_DEFAULTS), inj)
    svc.send_message("#engineering", "Deploy done")

    # Re-open store to verify persistence
    svc2 = SlackService(JsonStore(tmp_path / "s.json", {}), inj)
    result = svc2.search_messages("deploy")
    assert len(result["messages"]) == 1


def test_slack_invalid_channel_raises(tmp_path: Path) -> None:
    inj = ErrorInjector(0.0, "")
    svc = SlackService(JsonStore(tmp_path / "s.json", SLACK_DEFAULTS), inj)
    with pytest.raises(MockServiceError) as exc_info:
        svc.send_message("#unknown-channel", "hi")
    assert exc_info.value.code == ErrorCode.NOT_FOUND


def test_slack_error_injection_rate(tmp_path: Path) -> None:
    inj = ErrorInjector(1.0, "")  # 100% failure rate
    svc = SlackService(JsonStore(tmp_path / "s.json", SLACK_DEFAULTS), inj)
    with pytest.raises(MockServiceError):
        svc.list_channels()


def test_slack_force_error(tmp_path: Path) -> None:
    inj = ErrorInjector(0.0, "slack:rate_limit")
    svc = SlackService(JsonStore(tmp_path / "s.json", SLACK_DEFAULTS), inj)
    with pytest.raises(MockServiceError) as exc_info:
        svc.list_channels()
    assert exc_info.value.code == ErrorCode.RATE_LIMIT


def test_slack_force_error_other_service_not_affected(tmp_path: Path) -> None:
    inj = ErrorInjector(0.0, "jira:not_found")
    svc = SlackService(JsonStore(tmp_path / "s.json", SLACK_DEFAULTS), inj)
    # Should NOT raise — force_error targets jira, not slack
    result = svc.list_channels()
    assert result["ok"] is True


# ---------------------------------------------------------------------------
# Calendar: state and free-slot logic
# ---------------------------------------------------------------------------


def test_calendar_event_persists(tmp_path: Path) -> None:
    inj = ErrorInjector(0.0, "")
    svc = CalendarService(JsonStore(tmp_path / "c.json", CALENDAR_DEFAULTS), inj)
    svc.create_event("Retro", "2026-05-01T10:00:00", "2026-05-01T11:00:00", [])

    svc2 = CalendarService(JsonStore(tmp_path / "c.json", {}), inj)
    events = svc2.list_events("2026-05-01T00:00:00", "2026-05-02T00:00:00")["events"]
    assert any(e["title"] == "Retro" for e in events)


def test_calendar_timeout_injection(tmp_path: Path) -> None:
    inj = ErrorInjector(0.0, "calendar:timeout")
    svc = CalendarService(JsonStore(tmp_path / "c.json", CALENDAR_DEFAULTS), inj)
    with pytest.raises(MockServiceError) as exc_info:
        svc.list_events("2026-04-28T00:00:00", "2026-04-29T00:00:00")
    assert exc_info.value.code == ErrorCode.TIMEOUT


# ---------------------------------------------------------------------------
# Jira: counter and transitions
# ---------------------------------------------------------------------------


def test_jira_counter_increments(tmp_path: Path) -> None:
    inj = ErrorInjector(0.0, "")
    svc = JiraService(JsonStore(tmp_path / "j.json", JIRA_DEFAULTS), inj)
    r1 = svc.create_issue("Issue A")
    r2 = svc.create_issue("Issue B")
    assert r1["issue"]["key"] != r2["issue"]["key"]
    k1 = int(r1["issue"]["key"].split("-")[1])
    k2 = int(r2["issue"]["key"].split("-")[1])
    assert k2 == k1 + 1


def test_jira_invalid_transition_raises(tmp_path: Path) -> None:
    inj = ErrorInjector(0.0, "")
    svc = JiraService(JsonStore(tmp_path / "j.json", JIRA_DEFAULTS), inj)
    created = svc.create_issue("Bug")
    key = created["issue"]["key"]
    with pytest.raises(MockServiceError, match="Cannot transition"):
        svc.transition_issue(key, "Done")  # To Do → Done not allowed


# ---------------------------------------------------------------------------
# Email: outbox accumulates
# ---------------------------------------------------------------------------


def test_email_outbox_accumulates(tmp_path: Path) -> None:
    inj = ErrorInjector(0.0, "")
    svc = EmailService(JsonStore(tmp_path / "e.json", EMAIL_DEFAULTS), inj)
    svc.send_email(["a@x.com"], "First", "body1")
    svc.send_email(["b@x.com"], "Second", "body2")

    result = svc.search_email("", folder="outbox")
    assert len(result["messages"]) == 2


def test_email_search_all_folders(tmp_path: Path) -> None:
    inj = ErrorInjector(0.0, "")
    svc = EmailService(JsonStore(tmp_path / "e.json", EMAIL_DEFAULTS), inj)
    svc.send_email(["x@y.com"], "sprint query", "body")

    result = svc.search_email("sprint", folder="all")
    # inbox has "Sprint review preparation" from seed + outbox has "sprint query"
    assert len(result["messages"]) >= 2
