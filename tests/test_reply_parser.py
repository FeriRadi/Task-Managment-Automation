from src.parser.reply_parser import parse_reply_body, strip_html

VALID_BODY = """Task Update

Employee: Jane Doe
Date: 2026-07-12

| Jira Key | Status | Requested Due Date | Comment |
| -------- | ------ | ------------------- | ------- |
| SYS-231 | Completed | - | Completed yesterday |
| SYS-245 | In Progress | 2026-07-15 | Waiting for hardware |
| SYS-280 | Blocked | 2026-07-18 | Waiting for customer feedback |
"""


def test_parse_valid_reply_extracts_header_and_rows():
    parsed = parse_reply_body(VALID_BODY)

    assert parsed.employee_name == "Jane Doe"
    assert parsed.reply_date == "2026-07-12"
    assert parsed.is_valid_template
    assert len(parsed.updates) == 3

    first = parsed.updates[0]
    assert first.jira_key == "SYS-231"
    assert first.status == "Completed"
    assert first.requested_due_date is None  # "-" maps to None
    assert first.comment == "Completed yesterday"


def test_parse_reply_missing_employee_line_reports_error():
    body = VALID_BODY.replace("Employee: Jane Doe\n", "")
    parsed = parse_reply_body(body)

    assert any("Employee" in e for e in parsed.parse_errors)


def test_parse_reply_with_no_table_is_invalid():
    body = "Task Update\n\nEmployee: Jane Doe\nDate: 2026-07-12\n\nNo table here.\n"
    parsed = parse_reply_body(body)

    assert not parsed.is_valid_template
    assert any("table" in e.lower() for e in parsed.parse_errors)


def test_parse_reply_malformed_row_reports_error_but_keeps_valid_rows():
    body = VALID_BODY + "| SYS-999 | OnlyTwoColumns |\n"
    parsed = parse_reply_body(body)

    assert len(parsed.updates) == 3  # malformed row excluded
    assert any("Malformed" in e for e in parsed.parse_errors)


def test_strip_html_converts_basic_markup_to_text():
    html = "<html><body><p>Employee: Jane</p><br>Date: 2026-07-12</body></html>"
    text = strip_html(html)

    assert "Employee: Jane" in text
    assert "Date: 2026-07-12" in text
