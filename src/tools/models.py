"""Pydantic models for tool input/output contracts."""

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------
# Slack
# ---------------------------------------------------------------------------


class SlackSendMessageParams(StrictModel):
    channel: str = Field(min_length=1)
    text: str = Field(min_length=1)
    user: str = "agent"


class SlackSendMessageResult(StrictModel):
    ok: bool
    ts: str
    channel: str


class SlackChannel(StrictModel):
    id: str
    name: str
    is_member: bool


class SlackListChannelsResult(StrictModel):
    ok: bool
    channels: list[SlackChannel]


class SlackSearchMessagesParams(StrictModel):
    query: str
    channel: str | None = None


class SlackMessage(StrictModel):
    ts: str
    text: str
    user: str
    channel: str


class SlackSearchMessagesResult(StrictModel):
    ok: bool
    messages: list[SlackMessage]


# ---------------------------------------------------------------------------
# Calendar
# ---------------------------------------------------------------------------


class CalendarEvent(StrictModel):
    id: str
    title: str
    start: str
    end: str
    attendees: list[str]
    description: str


class CalendarCreateEventParams(StrictModel):
    title: str = Field(min_length=1)
    start: str
    end: str
    attendees: list[str]
    description: str = ""


class CalendarCreateEventResult(StrictModel):
    ok: bool
    event: CalendarEvent


class CalendarListEventsParams(StrictModel):
    start: str
    end: str


class CalendarListEventsResult(StrictModel):
    ok: bool
    events: list[CalendarEvent]


class CalendarFreeSlotParams(StrictModel):
    duration_minutes: int = Field(gt=0)
    after: str
    before: str


class CalendarSlot(StrictModel):
    start: str
    end: str


class CalendarFreeSlotResult(StrictModel):
    ok: bool
    slot: CalendarSlot | None
    message: str | None = None


# ---------------------------------------------------------------------------
# Jira
# ---------------------------------------------------------------------------


class JiraIssue(StrictModel):
    key: str
    summary: str
    description: str
    assignee: str
    priority: str
    status: str
    created: str


class JiraCreateIssueParams(StrictModel):
    summary: str = Field(min_length=1)
    description: str = ""
    assignee: str = ""
    priority: str = "Medium"


class JiraIssueResult(StrictModel):
    ok: bool
    issue: JiraIssue


class JiraGetIssueParams(StrictModel):
    key: str = Field(min_length=1)


class JiraTransitionIssueParams(StrictModel):
    key: str = Field(min_length=1)
    status: str = Field(min_length=1)
    assignee: str | None = None


# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------


class EmailSendParams(StrictModel):
    to: list[str] = Field(min_length=1)
    subject: str = Field(min_length=1)
    body: str
    cc: list[str] | None = None


class EmailSendResult(StrictModel):
    ok: bool
    id: str
    timestamp: str


class EmailSearchParams(StrictModel):
    query: str
    folder: str = "inbox"


class EmailMessage(StrictModel):
    id: str
    from_: str | None = Field(default=None, alias="from")
    to: list[str]
    cc: list[str]
    subject: str
    body: str
    timestamp: str


class EmailSearchResult(StrictModel):
    ok: bool
    messages: list[EmailMessage]
