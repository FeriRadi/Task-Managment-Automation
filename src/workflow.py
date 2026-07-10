"""High-level orchestration of the two weekly jobs:

1. ``send_reminders``   - Jira -> group by assignee -> Outlook send -> DB
2. ``process_replies``  - Outlook inbox -> match -> parse -> validate -> DB

Kept separate from ``main.py`` (CLI/entrypoint concerns) and from the
individual clients (single-responsibility), so each job can also be
invoked directly by the scheduler or by unit tests.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date
from pathlib import Path

import jinja2

from src.config_loader import Settings
from src.jira.client import JiraClient, JiraClientError
from src.models.domain import JiraIssue, ParsedUpdate, ReceivedReply, ReminderEmail
from src.outlook.client import OutlookClient, OutlookClientError
from src.parser.reply_parser import parse_reply_body, strip_html
from src.storage.database import Database
from src.utils.id_generator import generate_reminder_id
from src.validation.validators import validate_update

logger = logging.getLogger(__name__)


class ReminderWorkflow:
    """Coordinates Jira, Outlook, parsing, validation, and storage for
    both weekly jobs."""

    def __init__(
        self,
        settings: Settings,
        database: Database,
        jira_client: JiraClient | None = None,
        outlook_client: OutlookClient | None = None,
    ) -> None:
        self._settings = settings
        self._database = database
        self._jira = jira_client or JiraClient(settings)
        self._outlook = outlook_client or OutlookClient(settings)
        self._jinja_env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(str(settings.project_root)),
            autoescape=jinja2.select_autoescape(["html"]),
        )

    # ------------------------------------------------------------------
    # Job 1: send reminders
    # ------------------------------------------------------------------
    def send_reminders(self) -> int:
        """Fetch overdue issues, group by assignee, send one email per
        assignee. Returns the number of emails successfully sent."""
        execution_id = self._database.start_execution_log("send_reminders")
        sent_count = 0
        try:
            issues = self._jira.fetch_overdue_issues()
            self._database.save_jira_tasks(issues)

            grouped = self._group_by_assignee(issues)
            already_sent_today = self._database.count_reminders_sent_today()

            for i, (assignee_email, assignee_issues) in enumerate(grouped.items(), start=1):
                reminder_id = generate_reminder_id(
                    self._settings.email.reminder_id_prefix,
                    sequence=already_sent_today + i,
                )
                try:
                    self._send_one_reminder(reminder_id, assignee_email, assignee_issues)
                    sent_count += 1
                except OutlookClientError:
                    logger.exception("Failed to send reminder to %s", assignee_email)

            self._database.finish_execution_log(
                execution_id, "SUCCESS", f"Sent {sent_count} reminder(s) for {len(issues)} issue(s)"
            )
        except JiraClientError as exc:
            logger.exception("Jira access failed during send_reminders")
            self._database.finish_execution_log(execution_id, "FAILED", str(exc))
            raise
        except Exception as exc:  # pragma: no cover - safety net
            logger.exception("Unexpected failure during send_reminders")
            self._database.finish_execution_log(execution_id, "FAILED", str(exc))
            raise
        return sent_count

    @staticmethod
    def _group_by_assignee(issues: list[JiraIssue]) -> dict[str, list[JiraIssue]]:
        grouped: dict[str, list[JiraIssue]] = defaultdict(list)
        for issue in issues:
            grouped[issue.assignee_email].append(issue)
        return grouped

    def _send_one_reminder(
        self, reminder_id: str, assignee_email: str, issues: list[JiraIssue]
    ) -> None:
        assignee_name = issues[0].assignee_display_name
        self._database.upsert_employee(assignee_name, assignee_email)

        subject = f"{self._settings.email.subject_prefix} Overdue tasks for {assignee_name} ({reminder_id})"
        html_body = self._render_email(reminder_id, assignee_name, issues)

        entry_id, conversation_id, conversation_index = self._outlook.send_html_email(
            to_email=assignee_email, subject=subject, html_body=html_body
        )

        reminder = ReminderEmail(
            reminder_id=reminder_id,
            conversation_id=conversation_id,
            conversation_index=conversation_index,
            entry_id=entry_id,
            recipient_email=assignee_email,
            subject=subject,
            jira_keys=[i.jira_key for i in issues],
            status="SENT",
        )
        self._database.save_sent_email(reminder)
        logger.info(
            "Sent reminder %s to %s covering %d issue(s)",
            reminder_id, assignee_email, len(issues),
        )

    def _render_email(self, reminder_id: str, assignee_name: str, issues: list[JiraIssue]) -> str:
        template = self._jinja_env.get_template(self._settings.email.template_file)
        return template.render(
            reminder_id=reminder_id,
            assignee_name=assignee_name,
            tasks=[
                {"jira_key": i.jira_key, "summary": i.summary, "due_date": i.due_date or "N/A"}
                for i in issues
            ],
        )

    # ------------------------------------------------------------------
    # Job 2: process replies
    # ------------------------------------------------------------------
    def process_replies(self) -> int:
        """Scan the inbox for replies to reminder emails, parse and
        validate them, and persist results. Returns the number of new
        replies processed."""
        execution_id = self._database.start_execution_log("process_replies")
        processed_count = 0
        try:
            known_entry_ids = self._database.known_reply_entry_ids()

            for message in self._outlook.iter_recent_inbox_messages():
                if message.entry_id in known_entry_ids:
                    continue  # duplicate, already processed

                sent_email = self._match_reply_to_reminder(message)
                if sent_email is None:
                    continue  # unrelated email, ignore

                self._process_single_reply(message, sent_email)
                processed_count += 1

            self._database.finish_execution_log(
                execution_id, "SUCCESS", f"Processed {processed_count} new repl(y/ies)"
            )
        except OutlookClientError as exc:
            logger.exception("Outlook access failed during process_replies")
            self._database.finish_execution_log(execution_id, "FAILED", str(exc))
            raise
        except Exception as exc:  # pragma: no cover - safety net
            logger.exception("Unexpected failure during process_replies")
            self._database.finish_execution_log(execution_id, "FAILED", str(exc))
            raise
        return processed_count

    def _match_reply_to_reminder(self, message) -> object | None:  # sqlite3.Row | None
        """Match an inbox message to a previously sent reminder, first by
        ConversationID, then by Reminder ID embedded in the subject."""
        if message.conversation_id:
            match = self._database.get_sent_email_by_conversation_id(message.conversation_id)
            if match:
                return match

        reminder_id = self._extract_reminder_id_from_subject(message.subject)
        if reminder_id:
            return self._database.get_sent_email_by_reminder_id(reminder_id)

        return None

    @staticmethod
    def _extract_reminder_id_from_subject(subject: str) -> str | None:
        import re

        match = re.search(r"\bREM-\d{8}-\d{3}\b", subject or "")
        return match.group(0) if match else None

    def _process_single_reply(self, message, sent_email) -> None:
        body = message.body or strip_html(message.html_body)

        reply = ReceivedReply(
            reminder_id=sent_email["reminder_id"],
            conversation_id=message.conversation_id,
            entry_id=message.entry_id,
            sender_email=message.sender_email or "unknown@unknown.invalid",
            subject=message.subject,
            received_time=message.received_time,
            raw_body=body,
        )
        reply_id = self._database.save_received_reply(reply)

        parsed = parse_reply_body(body)
        if not parsed.is_valid_template:
            logger.warning(
                "Reply %s for reminder %s did not match the expected template: %s",
                message.entry_id, sent_email["reminder_id"], parsed.parse_errors,
            )

        known_keys = set((sent_email["jira_keys"] or "").split(","))
        validated_updates: list[ParsedUpdate] = [
            validate_update(u, known_keys, self._settings) for u in parsed.updates
        ]

        self._database.save_parsed_updates(reply_id, validated_updates)
        self._database.mark_reply_processed(reply_id)
