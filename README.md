# Jira Reminder & Outlook Reply Tracking

A Windows desktop-automation application that, every Saturday:

1. Queries Jira for overdue, unresolved issues you reported.
2. Groups them by assignee and sends **one** reminder email per assignee
   via Outlook Desktop (COM automation).
3. Later the same day, scans your Outlook Inbox for replies, parses them
   against a **fixed, predefined template** (no AI/LLM involved anywhere
   in this project), validates the content, and stores everything in a
   local SQLite database.
4. Generates HTML, Excel, and CSV reports summarizing who has replied,
   who hasn't, and what they reported.

---

## 1. Installation

**Prerequisites**

- Windows 11
- Python 3.12+
- Microsoft Outlook Desktop, installed and already configured with your
  mailbox (opened at least once so the MAPI profile exists)
- Access to a Jira Server / Data Center instance via REST API

**Steps**

```powershell
git clone <this-repo>
cd project
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Edit `.env` and fill in your Jira credentials (see below).

Initialize the database:

```powershell
python main.py init-db
```

---

## 2. Configuration

Configuration is split in two, deliberately:

| File                  | Purpose                                              |
|-----------------------|-------------------------------------------------------|
| `.env`                | Secrets: Jira URL, username, API token/password       |
| `config/config.yaml`  | Everything else: JQL, schedule, templates, DB path...  |

### `.env`

```
JIRA_BASE_URL=https://jira.mycompany.com
JIRA_USERNAME=my.username
JIRA_API_TOKEN=my-jira-api-token-or-password
JIRA_REPORTER=my.username
APP_CONFIG_PATH=config/config.yaml
APP_ENVIRONMENT=dev
```

### `config/config.yaml`

Key sections you will likely want to tune:

- `jira.jql` — the JQL template used to find overdue issues. Supports
  `{reporter}` and `{today}` placeholders.
- `outlook.reply_lookback_days` — how many days back to scan the Inbox
  for replies.
- `schedule.*` — day/time for the two weekly jobs.
- `reports.formats` — any subset of `html`, `xlsx`, `csv`.
- `validation.allowed_statuses` — the only Status values the reply
  parser will accept as valid (`Completed`, `In Progress`, `Blocked` by
  default).

No values are hardcoded in the source; everything above is read through
`src/config_loader.py`.

---

## 3. Running

### One-off, manual runs

```powershell
python main.py send-reminders      # Query Jira, send today's reminder emails
python main.py process-replies     # Scan Inbox, parse & store replies
python main.py generate-reports    # Rebuild HTML/Excel/CSV reports
```

### Long-running scheduler

```powershell
python main.py run-scheduler
```

This starts a foreground process that sleeps and wakes up to run
`send-reminders` and `process-replies` at the times configured in
`config/config.yaml` (Saturday morning / Saturday afternoon by default).
Keep this process running (e.g. via Windows Task Scheduler configured to
launch it at logon, or NSSM/a similar service wrapper) — it does not
daemonize itself.

---

## 4. Folder structure

```
project/
  config/            YAML configuration (business + logging)
  templates/          Jinja2 HTML email template
  database/            SQL schema + the SQLite file at runtime
  logs/                Rotating log files
  reports/             Generated HTML/Excel/CSV reports
  src/
    jira/              Jira REST client
    outlook/           Outlook COM automation wrapper
    parser/            Deterministic reply-table parser (no AI)
    validation/        Business-rule validation of parsed replies
    scheduler/         Weekly job scheduling (the `schedule` library)
    reporting/         Report generation (pandas)
    storage/           SQLite repository
    models/            Pydantic domain models
    utils/             Logging setup, Reminder ID generator
    config_loader.py   .env + YAML -> validated Settings object
  tests/               Unit tests (pytest)
  main.py              CLI entrypoint
  requirements.txt
  .env.example
```

---

## 5. The reply template (must be followed exactly)

Every reminder email asks the recipient to reply using this exact
layout. The parser is intentionally strict and does not attempt to
"understand" free-form text — this is a rules-based system, not AI.

```
Task Update

Employee: <name>
Date: <YYYY-MM-DD>

| Jira Key | Status | Requested Due Date | Comment |
| SYS-231  | Completed | - | Completed yesterday |
| SYS-245  | In Progress | 2026-07-15 | Waiting for hardware |
| SYS-280  | Blocked | 2026-07-18 | Waiting for customer feedback |
```

Allowed `Status` values are configured in `config/config.yaml` under
`validation.allowed_statuses` (`Completed`, `In Progress`, `Blocked` by
default). Rows with an unrecognized Jira key, invalid status, or badly
formatted date are still stored, but flagged with warnings so they show
up in reports for manual follow-up.

---

## 6. Database

SQLite database (default path `database/reminders.db`) with these
tables (see `database/schema.sql` for full DDL):

- `employees` — every assignee ever emailed
- `jira_tasks` — snapshot of overdue issues per run
- `sent_emails` — one row per reminder email sent (Reminder ID,
  ConversationID, ConversationIndex, EntryID, recipients, sent time)
- `received_replies` — raw metadata for every reply that matched a
  reminder
- `parsed_updates` — one row per Jira-key line extracted from a reply
- `execution_logs` — audit trail of every job run

The schema is plain SQL, so adding columns or tables for future
extensions is straightforward and does not require an ORM migration
tool.

---

## 7. Troubleshooting

### Common Outlook issues

- **"Could not connect to Outlook"** — Outlook Desktop must be installed
  and have been opened at least once under the same Windows user account
  running this script, so a MAPI profile exists.
- **COM automation security prompt** — some Outlook/Exchange security
  policies show a "A program is trying to access your Outlook data"
  dialog on first send. Approve it (or have your Exchange admin allow
  the specific accessing process) — this project uses standard COM
  automation and does not bypass or suppress that prompt.
- **Wrong account sends the email** — set `outlook.send_from_account` in
  `config/config.yaml` to the exact display name of the account/profile
  to send from.

### Common Jira issues

- **401 Unauthorized** — check `JIRA_USERNAME` / `JIRA_API_TOKEN` in
  `.env`. For Jira Server/Data Center this is typically your normal
  username and password or a Personal Access Token, not an Atlassian
  Cloud API token.
- **Empty results** — verify the JQL in `config/config.yaml` actually
  matches issues in your Jira project; test it directly in Jira's issue
  search first.
- **SSL errors on an internal Jira instance** — set
  `jira.verify_ssl: false` in `config/config.yaml` only if you understand
  and accept the security implications (self-signed certs), or better,
  install the internal CA certificate instead.

### Database

- **"Database is locked"** — another process (or a previous crashed run)
  still has the SQLite file open. Close any other running instance of
  this application; the busy timeout is configurable via
  `database.busy_timeout_ms`.

---

## 8. Screenshots

_Placeholder — add screenshots of a sample reminder email, the HTML
report, and the Excel report here once available in your environment._

---

## 9. Future extensions

The architecture (clean separation between Jira/Outlook/parser/
validation/storage/reporting, dependency-injected `Settings`, plain-SQL
schema) is designed to make the following straightforward additions
later, without this initial version implementing any of them:

- Microsoft Teams / Slack notifications
- Confluence integration
- LLM-based reply parsing (as an alternative, opt-in parser module)
- Automatic Jira comments / due date updates from parsed replies
- A dashboard or REST API on top of the existing SQLite data
- A web front-end

---

## 10. Running the tests

```powershell
pip install -r requirements.txt
pytest --cov=src --cov-report=term-missing
```

Outlook and Jira tests use mocked COM objects / HTTP responses
respectively, so the full suite runs without a live Jira server or
Outlook installation.
