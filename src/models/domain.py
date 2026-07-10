"""Domain models shared across the application.

All models are Pydantic models so that data coming from Jira, Outlook,
and parsed replies is validated at the boundary, before it ever reaches
business logic or the database layer.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, field_validator


class JiraIssue(BaseModel):
    """A single overdue Jira issue as returned by the Jira REST API."""

    jira_key: str = Field(..., description="Jira issue key, e.g. SYS-231")
    summary: str
    due_date: Optional[str] = Field(None, description="ISO date string, e.g. 2026-07-10")
    assignee_email: EmailStr
    assignee_display_name: str
    status: str
    resolution: Optional[str] = None

    class Config:
        frozen = True


class ReminderEmail(BaseModel):
    """Metadata describing a reminder email that was sent (or attempted)."""

    reminder_id: str
    conversation_id: Optional[str] = None
    conversation_index: Optional[str] = None
    entry_id: Optional[str] = None
    recipient_email: EmailStr
    subject: str
    sent_time: datetime = Field(default_factory=datetime.now)
    jira_keys: list[str]
    status: str = "SENT"


class ReceivedReply(BaseModel):
    """Raw metadata about an inbound email that was matched as a reply."""

    reminder_id: Optional[str] = None
    conversation_id: Optional[str] = None
    entry_id: str
    sender_email: EmailStr
    subject: Optional[str] = None
    received_time: Optional[datetime] = None
    raw_body: str


class ParsedUpdate(BaseModel):
    """A single Jira-key row extracted from a reply's Task Update table."""

    jira_key: str
    status: Optional[str] = None
    requested_due_date: Optional[str] = None
    comment: Optional[str] = None
    is_valid: bool = True
    validation_warnings: list[str] = Field(default_factory=list)

    @field_validator("jira_key")
    @classmethod
    def _uppercase_key(cls, value: str) -> str:
        return value.strip().upper()


class ParsedReply(BaseModel):
    """The full result of parsing one reply email: employee/date header
    plus every parsed task row."""

    employee_name: Optional[str] = None
    reply_date: Optional[str] = None
    updates: list[ParsedUpdate] = Field(default_factory=list)
    parse_errors: list[str] = Field(default_factory=list)

    @property
    def is_valid_template(self) -> bool:
        return not self.parse_errors and len(self.updates) > 0
