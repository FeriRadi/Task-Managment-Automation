-- =============================================================================
-- Schema for the Jira Reminder / Outlook Reply Tracking application.
-- SQLite dialect. Safe to run multiple times (CREATE TABLE IF NOT EXISTS).
-- =============================================================================

PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------------------
-- employees: one row per assignee we have ever emailed
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS employees (
    employee_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    display_name    TEXT NOT NULL,
    email_address   TEXT NOT NULL UNIQUE,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ---------------------------------------------------------------------------
-- jira_tasks: snapshot of every overdue issue we have seen, per run
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS jira_tasks (
    task_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    jira_key        TEXT NOT NULL,
    summary         TEXT NOT NULL,
    due_date        TEXT,
    assignee_email  TEXT NOT NULL,
    status          TEXT,
    resolution      TEXT,
    fetched_at      TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (jira_key, fetched_at)
);

CREATE INDEX IF NOT EXISTS idx_jira_tasks_key ON jira_tasks (jira_key);
CREATE INDEX IF NOT EXISTS idx_jira_tasks_assignee ON jira_tasks (assignee_email);

-- ---------------------------------------------------------------------------
-- sent_emails: one row per reminder email sent to an assignee
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sent_emails (
    reminder_id       TEXT PRIMARY KEY,
    conversation_id   TEXT,
    conversation_index TEXT,
    entry_id          TEXT,
    recipient_email   TEXT NOT NULL,
    subject           TEXT NOT NULL,
    sent_time         TEXT NOT NULL DEFAULT (datetime('now')),
    jira_keys         TEXT NOT NULL, -- comma-separated list of keys covered by this reminder
    status            TEXT NOT NULL DEFAULT 'SENT' -- SENT / FAILED
);

CREATE INDEX IF NOT EXISTS idx_sent_emails_conversation ON sent_emails (conversation_id);
CREATE INDEX IF NOT EXISTS idx_sent_emails_recipient ON sent_emails (recipient_email);

-- ---------------------------------------------------------------------------
-- received_replies: raw metadata about every reply email that matched
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS received_replies (
    reply_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    reminder_id       TEXT REFERENCES sent_emails (reminder_id),
    conversation_id   TEXT,
    entry_id          TEXT,
    sender_email      TEXT NOT NULL,
    subject           TEXT,
    received_time     TEXT,
    raw_body          TEXT,
    processed         INTEGER NOT NULL DEFAULT 0, -- 0/1
    created_at        TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (entry_id)
);

CREATE INDEX IF NOT EXISTS idx_received_replies_reminder ON received_replies (reminder_id);

-- ---------------------------------------------------------------------------
-- parsed_updates: one row per Jira key line inside a parsed reply table
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS parsed_updates (
    update_id           INTEGER PRIMARY KEY AUTOINCREMENT,
    reply_id            INTEGER NOT NULL REFERENCES received_replies (reply_id),
    jira_key            TEXT NOT NULL,
    status              TEXT,
    requested_due_date  TEXT,
    comment             TEXT,
    is_valid            INTEGER NOT NULL DEFAULT 1, -- 0/1
    validation_warnings TEXT, -- JSON-encoded list of warning strings
    created_at          TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_parsed_updates_reply ON parsed_updates (reply_id);
CREATE INDEX IF NOT EXISTS idx_parsed_updates_key ON parsed_updates (jira_key);

-- ---------------------------------------------------------------------------
-- execution_logs: one row per scheduler/manual run, for audit purposes
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS execution_logs (
    execution_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    job_name        TEXT NOT NULL, -- e.g. 'send_reminders', 'process_replies'
    started_at      TEXT NOT NULL DEFAULT (datetime('now')),
    finished_at     TEXT,
    status          TEXT NOT NULL DEFAULT 'RUNNING', -- RUNNING / SUCCESS / FAILED
    details         TEXT
);
