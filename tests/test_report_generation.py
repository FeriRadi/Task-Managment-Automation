import sqlite3
from unittest.mock import MagicMock

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
from src.reporting.report_generator import ReportGenerator


@pytest.fixture
def settings(tmp_path):
    return Settings(
        project_root=tmp_path,
        jira_base_url="https://jira.example.com",
        jira_username="user",
        jira_api_token="token",
        jira_reporter="user",
        jira=JiraConfig(jql="reporter = x", fields=["key"]),
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
        reports=ReportsConfig(
            output_folder="reports", formats=["html", "csv", "xlsx"], filename_prefix="report"
        ),
        logging=LoggingConfig(),
        validation=ValidationConfig(allowed_statuses=["Completed", "In Progress", "Blocked"]),
    )


def _make_row(d: dict) -> sqlite3.Row:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    cols = ", ".join(d.keys())
    placeholders = ", ".join("?" for _ in d)
    conn.execute(f"CREATE TABLE t ({', '.join(f'{k} TEXT' for k in d)})")
    conn.execute(f"INSERT INTO t ({cols}) VALUES ({placeholders})", list(d.values()))
    return conn.execute("SELECT * FROM t").fetchone()


def test_generate_all_writes_configured_formats(settings):
    fake_database = MagicMock()
    fake_database.fetch_report_rows.return_value = [
        _make_row(
            {
                "employee": "Jane Doe",
                "jira_key": "SYS-231",
                "summary": "Fix the thing",
                "due_date": "2026-07-01",
                "reported_status": "Completed",
                "requested_due_date": None,
                "comment": "Done",
                "reply_received": "Yes",
                "reply_time": "2026-07-11 09:00:00",
            }
        )
    ]

    generator = ReportGenerator(settings, fake_database)
    paths = generator.generate_all()

    assert len(paths) == 3
    for path in paths:
        assert path.exists()
        assert path.stat().st_size > 0


def test_generate_all_handles_empty_data(settings):
    fake_database = MagicMock()
    fake_database.fetch_report_rows.return_value = []

    generator = ReportGenerator(settings, fake_database)
    paths = generator.generate_all()

    assert len(paths) == 3
    for path in paths:
        assert path.exists()
