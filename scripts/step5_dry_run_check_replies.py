"""STEP 5 - Dry-run: scan the Outlook Inbox and show what WOULD be
parsed, without writing anything to the database.

Useful to confirm reply detection + template parsing before trusting it
to run unattended.

Run from the project root:
    python scripts/step5_dry_run_check_replies.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config_loader import load_settings
from src.outlook.client import OutlookClient, OutlookClientError
from src.parser.reply_parser import parse_reply_body, strip_html


def main() -> None:
    settings = load_settings()
    client = OutlookClient(settings)

    print(f"Scanning Inbox, last {settings.outlook.reply_lookback_days} day(s)...\n")

    try:
        messages = list(client.iter_recent_inbox_messages())
    except OutlookClientError as exc:
        print(f"❌ Outlook read FAILED: {exc}")
        sys.exit(1)

    print(f"Found {len(messages)} message(s) in the lookback window.\n")

    for msg in messages:
        print(f"--- {msg.subject}")
        print(f"    From: {msg.sender_email}  Received: {msg.received_time}")
        print(f"    ConversationID: {msg.conversation_id}")

        body = msg.body or strip_html(msg.html_body)
        parsed = parse_reply_body(body)

        if parsed.is_valid_template:
            print(f"    ✅ Valid template. Employee={parsed.employee_name}, Date={parsed.reply_date}")
            for u in parsed.updates:
                print(f"       {u.jira_key}: {u.status} | due {u.requested_due_date} | {u.comment}")
        else:
            print(f"    ⚠️  Not a valid Task Update reply (or unrelated email): {parsed.parse_errors}")
        print()


if __name__ == "__main__":
    main()
