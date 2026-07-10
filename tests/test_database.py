from datetime import datetime

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
from src.models.domain import JiraIssue, ParsedUpdate, ReceivedReply, ReminderEmail
from src.storage.database import Database


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
        reports=ReportsConfig(output_folder="reports", formats=["html"], filename_prefix="report"),
        logging=LoggingConfig(),
        validation=ValidationConfig(allowed_statuses=["Completed", "In Progress", "Blocked"]),
    )


@pytest.fixture
def database(settings):
    # Copy the real schema file next to the temp project root so
    # Database can find it via settings.resolve_path().
    import shutil
    from pathlib import Path

    real_schema = Path(__file__).resolve().parent.parent / "database" / "schema.sql"
    target = settings.resolve_path("database/schema.sql")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(real_schema, target)

    db = Database(settings)
    db.initialize_schema()
    return db


def test_upsert_employee_creates_then_updates(database):
    emp_id_1 = database.upsert_employee("Jane Doe", "jane@example.com")
    emp_id_2 = database.upsert_employee("Jane D. Doe", "jane@example.com")

    assert emp_id_1 == emp_id_2  # same email -> same row, updated in place


def test_save_and_fetch_jira_tasks(database):
    issue = JiraIssue(
        jira_key="SYS-231",
        summary="Fix the thing",
        due_date="2026-07-01",
        assignee_email="jane@example.com",
        assignee_display_name="Jane Doe",
        status="Open",
        resolution=None,
    )
    database.save_jira_tasks([issue])
    rows = database.fetch_report_rows()

    assert len(rows) == 1
    assert rows[0]["jira_key"] == "SYS-231"


def test_save_and_retrieve_sent_email_by_reminder_id(database):
    reminder = ReminderEmail(
        reminder_id="REM-20260711-001",
        conversation_id="conv-123",
        recipient_email="jane@example.com",
        subject="[Jira Reminder] Overdue tasks",
        jira_keys=["SYS-231", "SYS-245"],
    )
    database.save_sent_email(reminder)

    row = database.get_sent_email_by_reminder_id("REM-20260711-001")
    assert row is not None
    assert row["recipient_email"] == "jane@example.com"
    assert row["jira_keys"] == "SYS-231,SYS-245"

    by_conv = database.get_sent_email_by_conversation_id("conv-123")
    assert by_conv["reminder_id"] == "REM-20260711-001"


def test_duplicate_reply_detection_via_known_entry_ids(database):
    reply = ReceivedReply(
        reminder_id="REM-20260711-001",
        conversation_id="conv-123",
        entry_id="entry-1",
        sender_email="jane@example.com",
        subject="RE: Overdue tasks",
        received_time=datetime.now(),
        raw_body="Task Update...",
    )
    reply_id = database.save_received_reply(reply)
    assert "entry-1" in database.known_reply_entry_ids()

    updates = [ParsedUpdate(jira_key="SYS-231", status="Completed")]
    database.save_parsed_updates(reply_id, updates)
    database.mark_reply_processed(reply_id)


def test_execution_log_lifecycle(database):
    execution_id = database.start_execution_log("send_reminders")
    database.finish_execution_log(execution_id, "SUCCESS", "Sent 2 reminders")
    # No exception means success; detailed row-level assertions would
    # require an extra getter, which isn't part of the public API needed
    # by the application today.
