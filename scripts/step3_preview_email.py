"""STEP 3 - Build the actual email HTML (Jinja2 template) without
sending anything.

Writes one preview .html file per assignee into scripts/output_preview/
so you can open them in a browser and check formatting before Outlook
is ever touched.

Run from the project root:
    python scripts/step3_preview_email.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config_loader import load_settings
from src.jira.client import JiraClient, JiraClientError
from src.utils.id_generator import generate_reminder_id
from src.workflow import ReminderWorkflow


def main() -> None:
    settings = load_settings()
    client = JiraClient(settings)

    try:
        issues = client.fetch_overdue_issues()
    except JiraClientError as exc:
        print(f"❌ Jira connection FAILED: {exc}")
        sys.exit(1)

    if not issues:
        print("No overdue issues found - nothing to preview.")
        return

    # We only need the email-rendering half of the workflow here, so we
    # build a ReminderWorkflow but never call send_reminders/process_replies.
    workflow = ReminderWorkflow(settings, database=None)  # type: ignore[arg-type]

    grouped = ReminderWorkflow._group_by_assignee(issues)
    out_dir = Path(__file__).resolve().parent / "output_preview"
    out_dir.mkdir(exist_ok=True)

    for i, (assignee_email, assignee_issues) in enumerate(grouped.items(), start=1):
        reminder_id = generate_reminder_id(settings.email.reminder_id_prefix, sequence=i)
        assignee_name = assignee_issues[0].assignee_display_name

        html = workflow._render_email(reminder_id, assignee_name, assignee_issues)

        safe_name = assignee_email.replace("@", "_at_").replace(".", "_")
        out_path = out_dir / f"preview_{safe_name}.html"
        out_path.write_text(html, encoding="utf-8")
        print(f"✅ Wrote preview for {assignee_name} <{assignee_email}> -> {out_path}")

    print(f"\nOpen the .html files in {out_dir} in your browser to review formatting.")


if __name__ == "__main__":
    main()
