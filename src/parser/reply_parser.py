"""Deterministic, rule-based parser for reply emails.

This parser intentionally uses only string operations and regular
expressions -- no AI/LLM involved, as required. It expects the exact
template distributed in the reminder email:

    Task Update

    Employee: <name>
    Date: <YYYY-MM-DD>

    | Jira Key | Status | Requested Due Date | Comment |
    | SYS-231  | Completed | - | Completed yesterday |
    ...

The parser is deliberately strict: any row that doesn't match the
expected pipe-delimited shape is reported as a parse error rather than
guessed at.
"""
from __future__ import annotations

import re
from html import unescape

from src.models.domain import ParsedReply, ParsedUpdate

_EMPLOYEE_RE = re.compile(r"^\s*Employee\s*:\s*(.+)$", re.IGNORECASE | re.MULTILINE)
_DATE_RE = re.compile(r"^\s*Date\s*:\s*(.+)$", re.IGNORECASE | re.MULTILINE)

# A table row looks like: | SYS-231 | Completed | - | Completed yesterday |
_TABLE_ROW_RE = re.compile(r"^\s*\|(.+)\|\s*$")

# Rows that are just separators, e.g. | -------- | ------ | ... |
_SEPARATOR_ROW_RE = re.compile(r"^[\s|:\-]+$")

_HEADER_KEYWORDS = ("jira key", "status", "requested due date", "comment")


def strip_html(html_body: str) -> str:
    """Very small, dependency-free HTML-to-text conversion, good enough
    for Outlook's typically simple reply formatting. Used as a fallback
    when only ``HTMLBody`` is available for a reply.
    """
    text = re.sub(r"(?is)<br\s*/?>", "\n", html_body)
    text = re.sub(r"(?is)</p>|</tr>|</div>", "\n", text)
    text = re.sub(r"(?is)<td[^>]*>", "|", text)
    text = re.sub(r"(?is)<[^>]+>", "", text)
    return unescape(text)


def _extract_table_rows(body: str) -> list[list[str]]:
    """Return a list of cell-lists for every non-header, non-separator
    pipe-delimited row found in the body."""
    rows: list[list[str]] = []
    for line in body.splitlines():
        match = _TABLE_ROW_RE.match(line)
        if not match:
            continue
        raw_cells = match.group(1)
        if _SEPARATOR_ROW_RE.match(raw_cells):
            continue
        cells = [cell.strip() for cell in raw_cells.split("|")]
        lowered = " ".join(cells).lower()
        if any(keyword in lowered for keyword in _HEADER_KEYWORDS):
            continue  # this is the header row, skip it
        if cells:
            rows.append(cells)
    return rows


def parse_reply_body(plain_text_body: str) -> ParsedReply:
    """Parse a reply body against the fixed Task Update template.

    Returns a :class:`ParsedReply`. If the body does not contain a
    recognizable table at all, ``parse_errors`` will be non-empty and
    ``is_valid_template`` will be ``False``; callers should treat this as
    an invalid-template reply rather than raising.
    """
    parse_errors: list[str] = []

    employee_match = _EMPLOYEE_RE.search(plain_text_body)
    date_match = _DATE_RE.search(plain_text_body)

    employee_name = employee_match.group(1).strip() if employee_match else None
    reply_date = date_match.group(1).strip() if date_match else None

    if not employee_match:
        parse_errors.append("Missing 'Employee:' line")
    if not date_match:
        parse_errors.append("Missing 'Date:' line")

    rows = _extract_table_rows(plain_text_body)
    if not rows:
        parse_errors.append("No task update table rows found")

    updates: list[ParsedUpdate] = []
    for row in rows:
        if len(row) < 4:
            parse_errors.append(f"Malformed table row (expected 4 columns): {row}")
            continue
        jira_key, status, requested_due_date, comment = row[0], row[1], row[2], row[3]
        if not jira_key:
            parse_errors.append(f"Table row missing Jira Key: {row}")
            continue
        updates.append(
            ParsedUpdate(
                jira_key=jira_key,
                status=status or None,
                requested_due_date=None if requested_due_date in ("-", "") else requested_due_date,
                comment=comment or None,
            )
        )

    return ParsedReply(
        employee_name=employee_name,
        reply_date=reply_date,
        updates=updates,
        parse_errors=parse_errors,
    )
