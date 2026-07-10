"""Tests for the Outlook wrapper.

Since ``win32com`` only works on Windows with Outlook installed, these
tests exercise the client's logic by monkeypatching the private
``_connect``/``_app`` internals rather than importing real COM objects.
This keeps the test suite runnable in CI on any platform.
"""
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from src.config_loader import (
    DatabaseConfig,
    EmailConfig,
    JiraConfig,
    LoggingConfig,
    OutlookConfig,
    ReportsConfig,
    ScheduleConfig,
    Settings,
    ValidationConfig,
)
from src.outlook.client import OutlookClient


@pytest.fixture
def settings(tmp_path):
    return Settings(
        project_root=tmp_path,
        jira_base_url="https://jira.example.com",
        jira_username="user",
        jira_api_token="token",
        jira_reporter="user",
        jira=JiraConfig(jql="reporter = x", fields=["key"]),
        outlook=OutlookConfig(reply_lookback_days=7, send_delay_seconds=0),
        email=EmailConfig(
            subject_prefix="[Jira Reminder]",
            reminder_id_prefix="REM",
            template_file="templates/reminder_email.html",
            sender_display_name="Bot",
        ),
        schedule=ScheduleConfig(
            send_reminders_day="saturday",
            send_reminders_time="08:00",
            process_replies_day="saturday",
            process_replies_time="16:00",
        ),
        database=DatabaseConfig(path="database/test.db", schema_file="database/schema.sql"),
        reports=ReportsConfig(output_folder="reports", formats=["html"], filename_prefix="report"),
        logging=LoggingConfig(),
        validation=ValidationConfig(allowed_statuses=["Completed", "In Progress", "Blocked"]),
    )


class _FakeMailItem:
    def __init__(self):
        self.To = None
        self.Subject = None
        self.HTMLBody = None
        self.EntryID = "entry-abc"
        self.ConversationID = "conv-abc"
        self.ConversationIndex = "idx-abc"
        self.sent = False

    def Send(self):
        self.sent = True


class _FakeApp:
    def __init__(self):
        self.created_items = []

    def CreateItem(self, item_type):
        item = _FakeMailItem()
        self.created_items.append(item)
        return item


def test_send_html_email_populates_mail_item_and_returns_ids(settings):
    client = OutlookClient(settings)
    client._app = _FakeApp()  # bypass real COM connection
    client._namespace = SimpleNamespace()

    entry_id, conversation_id, conversation_index = client.send_html_email(
        to_email="jane@example.com", subject="Test subject", html_body="<p>Hi</p>"
    )

    sent_item = client._app.created_items[0]
    assert sent_item.To == "jane@example.com"
    assert sent_item.Subject == "Test subject"
    assert sent_item.HTMLBody == "<p>Hi</p>"
    assert sent_item.sent is True
    assert entry_id == "entry-abc"
    assert conversation_id == "conv-abc"
    assert conversation_index == "idx-abc"


class _FakeMailReadItem:
    def __init__(self, entry_id, received_time, subject, sender_email, body):
        self.Class = 43
        self.EntryID = entry_id
        self.ConversationID = f"conv-{entry_id}"
        self.ConversationIndex = f"idx-{entry_id}"
        self.Subject = subject
        self.ReceivedTime = received_time
        self.Body = body
        self.HTMLBody = f"<p>{body}</p>"
        self.SenderEmailAddress = sender_email
        self.Sender = None


class _FakeItems(list):
    def Sort(self, *_args, **_kwargs):
        self.sort(key=lambda i: i.ReceivedTime, reverse=True)


class _FakeInbox:
    def __init__(self, items):
        self.Items = _FakeItems(items)


def test_iter_recent_inbox_messages_filters_by_lookback_window(settings):
    client = OutlookClient(settings)
    client._app = SimpleNamespace()
    client._namespace = SimpleNamespace()

    now = datetime.now()
    recent = _FakeMailReadItem("e1", now - timedelta(days=1), "RE: Overdue tasks", "jane@example.com", "Task Update")
    old = _FakeMailReadItem("e2", now - timedelta(days=30), "RE: Overdue tasks", "jane@example.com", "Task Update")

    client._get_inbox = lambda: _FakeInbox([recent, old])

    messages = list(client.iter_recent_inbox_messages())
    entry_ids = [m.entry_id for m in messages]

    assert "e1" in entry_ids
    assert "e2" not in entry_ids
