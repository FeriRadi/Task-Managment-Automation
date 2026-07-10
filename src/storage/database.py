"""SQLite storage layer.

A thin, explicit repository-style wrapper around ``sqlite3`` -- no ORM,
so the schema in ``database/schema.sql`` remains the single source of
truth and is easy to extend (as required: employees, jira_tasks,
sent_emails, received_replies, parsed_updates, execution_logs).
"""
from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

from src.config_loader import Settings
from src.models.domain import JiraIssue, ParsedUpdate, ReceivedReply, ReminderEmail

logger = logging.getLogger(__name__)


class DatabaseError(Exception):
    """Raised for unrecoverable database failures (e.g. locked database
    after retries are exhausted)."""


class Database:
    """Repository for all persistence needs of this application.

    One instance is expected to live for the duration of a single
    scheduler run / CLI invocation.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._db_path = settings.resolve_path(settings.database.path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._schema_path = settings.resolve_path(settings.database.schema_file)

    def initialize_schema(self) -> None:
        """Run the SQL schema script. Safe to call on every startup."""
        if not self._schema_path.exists():
            raise DatabaseError(f"Schema file not found: {self._schema_path}")
        schema_sql = self._schema_path.read_text(encoding="utf-8")
        with self._connect() as conn:
            try:
                conn.executescript(schema_sql)
            except sqlite3.Error as exc:
                raise DatabaseError("Failed to initialize database schema") from exc
        logger.info("Database schema initialized at %s", self._db_path)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        try:
            conn = sqlite3.connect(
                str(self._db_path),
                timeout=self._settings.database.busy_timeout_ms / 1000,
            )
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
        except sqlite3.OperationalError as exc:
            raise DatabaseError(f"Could not open database at {self._db_path}: {exc}") from exc

        try:
            yield conn
            conn.commit()
        except sqlite3.OperationalError as exc:
            conn.rollback()
            if "locked" in str(exc).lower():
                raise DatabaseError("Database is locked by another process") from exc
            raise DatabaseError(f"Database operation failed: {exc}") from exc
        except sqlite3.Error as exc:
            conn.rollback()
            raise DatabaseError(f"Database operation failed: {exc}") from exc
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # employees
    # ------------------------------------------------------------------
    def upsert_employee(self, display_name: str, email_address: str) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                "SELECT employee_id FROM employees WHERE email_address = ?",
                (email_address,),
            )
            row = cur.fetchone()
            if row:
                conn.execute(
                    "UPDATE employees SET display_name = ?, updated_at = datetime('now') "
                    "WHERE employee_id = ?",
                    (display_name, row["employee_id"]),
                )
                return int(row["employee_id"])

            cur = conn.execute(
                "INSERT INTO employees (display_name, email_address) VALUES (?, ?)",
                (display_name, email_address),
            )
            return int(cur.lastrowid)

    # ------------------------------------------------------------------
    # jira_tasks
    # ------------------------------------------------------------------
    def save_jira_tasks(self, issues: list[JiraIssue]) -> None:
        with self._connect() as conn:
            conn.executemany(
                """
                INSERT OR IGNORE INTO jira_tasks
                    (jira_key, summary, due_date, assignee_email, status, resolution)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (i.jira_key, i.summary, i.due_date, i.assignee_email, i.status, i.resolution)
                    for i in issues
                ],
            )

    # ------------------------------------------------------------------
    # sent_emails
    # ------------------------------------------------------------------
    def count_reminders_sent_today(self) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                "SELECT COUNT(*) AS cnt FROM sent_emails WHERE date(sent_time) = date('now')"
            )
            return int(cur.fetchone()["cnt"])

    def save_sent_email(self, reminder: ReminderEmail) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO sent_emails
                    (reminder_id, conversation_id, conversation_index, entry_id,
                     recipient_email, subject, sent_time, jira_keys, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    reminder.reminder_id,
                    reminder.conversation_id,
                    reminder.conversation_index,
                    reminder.entry_id,
                    reminder.recipient_email,
                    reminder.subject,
                    reminder.sent_time.isoformat(sep=" ", timespec="seconds"),
                    ",".join(reminder.jira_keys),
                    reminder.status,
                ),
            )

    def get_sent_email_by_reminder_id(self, reminder_id: str) -> Optional[sqlite3.Row]:
        with self._connect() as conn:
            cur = conn.execute(
                "SELECT * FROM sent_emails WHERE reminder_id = ?", (reminder_id,)
            )
            return cur.fetchone()

    def get_sent_email_by_conversation_id(self, conversation_id: str) -> Optional[sqlite3.Row]:
        with self._connect() as conn:
            cur = conn.execute(
                "SELECT * FROM sent_emails WHERE conversation_id = ?", (conversation_id,)
            )
            return cur.fetchone()

    def get_all_sent_emails(self) -> list[sqlite3.Row]:
        with self._connect() as conn:
            return conn.execute("SELECT * FROM sent_emails ORDER BY sent_time DESC").fetchall()

    # ------------------------------------------------------------------
    # received_replies / parsed_updates
    # ------------------------------------------------------------------
    def known_reply_entry_ids(self) -> set[str]:
        with self._connect() as conn:
            rows = conn.execute("SELECT entry_id FROM received_replies").fetchall()
            return {row["entry_id"] for row in rows}

    def save_received_reply(self, reply: ReceivedReply) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO received_replies
                    (reminder_id, conversation_id, entry_id, sender_email,
                     subject, received_time, raw_body, processed)
                VALUES (?, ?, ?, ?, ?, ?, ?, 0)
                """,
                (
                    reply.reminder_id,
                    reply.conversation_id,
                    reply.entry_id,
                    reply.sender_email,
                    reply.subject,
                    reply.received_time.isoformat(sep=" ", timespec="seconds")
                    if reply.received_time
                    else None,
                    reply.raw_body,
                ),
            )
            return int(cur.lastrowid)

    def mark_reply_processed(self, reply_id: int) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE received_replies SET processed = 1 WHERE reply_id = ?", (reply_id,)
            )

    def save_parsed_updates(self, reply_id: int, updates: list[ParsedUpdate]) -> None:
        with self._connect() as conn:
            conn.executemany(
                """
                INSERT INTO parsed_updates
                    (reply_id, jira_key, status, requested_due_date, comment,
                     is_valid, validation_warnings)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        reply_id,
                        u.jira_key,
                        u.status,
                        u.requested_due_date,
                        u.comment,
                        int(u.is_valid),
                        json.dumps(u.validation_warnings),
                    )
                    for u in updates
                ],
            )

    # ------------------------------------------------------------------
    # execution_logs
    # ------------------------------------------------------------------
    def start_execution_log(self, job_name: str) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO execution_logs (job_name, status) VALUES (?, 'RUNNING')",
                (job_name,),
            )
            return int(cur.lastrowid)

    def finish_execution_log(self, execution_id: int, status: str, details: str = "") -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE execution_logs
                SET finished_at = datetime('now'), status = ?, details = ?
                WHERE execution_id = ?
                """,
                (status, details, execution_id),
            )

    # ------------------------------------------------------------------
    # Reporting helpers
    # ------------------------------------------------------------------
    def fetch_report_rows(self) -> list[sqlite3.Row]:
        """Return one row per (employee, jira task) combining reminder
        and reply status, for use by the reporting module."""
        query = """
            SELECT
                e.display_name    AS employee,
                jt.jira_key       AS jira_key,
                jt.summary        AS summary,
                jt.due_date       AS due_date,
                se.reminder_id    AS reminder_id,
                se.sent_time      AS reminder_sent_time,
                pu.status         AS reported_status,
                pu.requested_due_date AS requested_due_date,
                pu.comment        AS comment,
                rr.received_time  AS reply_time,
                CASE WHEN rr.reply_id IS NOT NULL THEN 'Yes' ELSE 'No' END AS reply_received
            FROM jira_tasks jt
            LEFT JOIN employees e ON e.email_address = jt.assignee_email
            LEFT JOIN sent_emails se
                ON instr(',' || se.jira_keys || ',', ',' || jt.jira_key || ',') > 0
            LEFT JOIN received_replies rr ON rr.reminder_id = se.reminder_id
            LEFT JOIN parsed_updates pu
                ON pu.reply_id = rr.reply_id AND pu.jira_key = jt.jira_key
            GROUP BY jt.jira_key, jt.fetched_at
            ORDER BY employee, jt.jira_key
        """
        with self._connect() as conn:
            return conn.execute(query).fetchall()
