import pytest
import requests

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
from src.jira.client import JiraClient, JiraClientError


@pytest.fixture
def settings(tmp_path):
    return Settings(
        project_root=tmp_path,
        jira_base_url="https://jira.example.com",
        jira_username="user",
        jira_api_token="token",
        jira_reporter="user",
        jira=JiraConfig(jql="reporter = {reporter} AND duedate <= {today}", fields=["key", "summary"]),
        outlook=OutlookConfig(),
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


class _FakeResponse:
    def __init__(self, status_code=200, json_data=None, text=""):
        self.status_code = status_code
        self._json_data = json_data or {}
        self.text = text
        self.ok = 200 <= status_code < 300

    def json(self):
        return self._json_data


def test_fetch_overdue_issues_parses_valid_response(settings, monkeypatch):
    client = JiraClient(settings)

    fake_payload = {
        "issues": [
            {
                "key": "SYS-231",
                "fields": {
                    "summary": "Fix the thing",
                    "duedate": "2026-07-01",
                    "assignee": {"emailAddress": "jane@example.com", "displayName": "Jane Doe"},
                    "status": {"name": "Open"},
                    "resolution": None,
                },
            }
        ]
    }

    monkeypatch.setattr(
        client._session, "get", lambda *a, **kw: _FakeResponse(200, fake_payload)
    )

    issues = client.fetch_overdue_issues()
    assert len(issues) == 1
    assert issues[0].jira_key == "SYS-231"
    assert issues[0].assignee_email == "jane@example.com"


def test_fetch_overdue_issues_skips_unassigned(settings, monkeypatch):
    client = JiraClient(settings)
    fake_payload = {
        "issues": [
            {"key": "SYS-999", "fields": {"summary": "Orphan task", "assignee": None, "status": {}}}
        ]
    }
    monkeypatch.setattr(
        client._session, "get", lambda *a, **kw: _FakeResponse(200, fake_payload)
    )

    issues = client.fetch_overdue_issues()
    assert issues == []


def test_fetch_overdue_issues_raises_on_auth_failure(settings, monkeypatch):
    client = JiraClient(settings)
    monkeypatch.setattr(client._session, "get", lambda *a, **kw: _FakeResponse(401))

    with pytest.raises(JiraClientError, match="authentication failed"):
        client.fetch_overdue_issues()


def test_fetch_overdue_issues_raises_on_connection_error(settings, monkeypatch):
    client = JiraClient(settings)

    def _raise(*a, **kw):
        raise requests.exceptions.ConnectionError("boom")

    monkeypatch.setattr(client._session, "get", _raise)

    with pytest.raises(JiraClientError, match="Could not connect"):
        client.fetch_overdue_issues()
