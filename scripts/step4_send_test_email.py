"""STEP 4 - Send ONE real email through Outlook, to a recipient you
choose (e.g. yourself), so you can confirm Outlook automation works
before the app ever emails a real colleague.

This does NOT read from Jira and does NOT write to the database - it
sends a fixed, obviously-labelled test message.

Run from the project root:
    python scripts/step4_send_test_email.py your.email@company.com
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config_loader import load_settings
from src.outlook.client import OutlookClient, OutlookClientError


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python scripts/step4_send_test_email.py <recipient_email>")
        sys.exit(1)

    recipient = sys.argv[1]
    settings = load_settings()
    client = OutlookClient(settings)

    subject = "[Jira Reminder] TEST - Outlook automation check"
    html_body = (
        "<p>This is a test email sent by the Outlook COM automation wrapper.</p>"
        "<p>If you can read this, sending works. Reminder ID: <b>REM-TEST-000</b></p>"
    )

    try:
        entry_id, conversation_id, conversation_index = client.send_html_email(
            to_email=recipient, subject=subject, html_body=html_body
        )
    except OutlookClientError as exc:
        print(f"❌ Outlook send FAILED: {exc}")
        sys.exit(1)

    print(f"✅ Test email sent to {recipient}")
    print(f"   EntryID           : {entry_id}")
    print(f"   ConversationID    : {conversation_id}")
    print(f"   ConversationIndex : {conversation_index}")
    print("\nCheck the recipient's inbox to confirm it arrived and looks right.")


if __name__ == "__main__":
    main()
