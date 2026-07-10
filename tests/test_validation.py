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
from src.models.domain import ParsedUpdate
from src.validation.validators import validate_update


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
        database=DatabaseConfig(path="database/reminders.db", schema_file="database/schema.sql"),
        reports=ReportsConfig(output_folder="reports", formats=["html"], filename_prefix="report"),
        logging=LoggingConfig(),
        validation=ValidationConfig(allowed_statuses=["Completed", "In Progress", "Blocked"]),
    )


def test_validate_update_known_key_allowed_status_is_valid(settings):
    update = ParsedUpdate(
        jira_key="SYS-231", status="Completed", requested_due_date=None, comment="done"
    )
    result = validate_update(update, known_jira_keys={"SYS-231"}, settings=settings)

    assert result.is_valid
    assert result.validation_warnings == []


def test_validate_update_unknown_key_flags_warning(settings):
    update = ParsedUpdate(jira_key="SYS-999", status="Completed")
    result = validate_update(update, known_jira_keys={"SYS-231"}, settings=settings)

    assert not result.is_valid
    assert any("not part of the original reminder" in w for w in result.validation_warnings)


def test_validate_update_invalid_status_flags_warning(settings):
    update = ParsedUpdate(jira_key="SYS-231", status="NotARealStatus")
    result = validate_update(update, known_jira_keys={"SYS-231"}, settings=settings)

    assert not result.is_valid
    assert any("allowed values" in w for w in result.validation_warnings)


def test_validate_update_bad_date_format_flags_warning(settings):
    update = ParsedUpdate(jira_key="SYS-231", status="In Progress", requested_due_date="15/07/2026")
    result = validate_update(update, known_jira_keys={"SYS-231"}, settings=settings)

    assert not result.is_valid
    assert any("does not match expected format" in w for w in result.validation_warnings)


def test_validate_update_blocked_without_due_date_flags_warning(settings):
    update = ParsedUpdate(jira_key="SYS-231", status="Blocked", requested_due_date=None)
    result = validate_update(update, known_jira_keys={"SYS-231"}, settings=settings)

    assert not result.is_valid
    assert any("Blocked" in w for w in result.validation_warnings)
