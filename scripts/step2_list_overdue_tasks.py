"""STEP 2 - List overdue tasks grouped by assignee (the colleagues who
will each get one email).

Still no Outlook, no database writes. Just Jira + grouping logic, so you
can eyeball exactly who would get emailed and with which tasks before
anything is sent.

Run from the project root:
    python scripts/step2_list_overdue_tasks.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config_loader import load_settings
from src.jira.client import JiraClient, JiraClientError
from src.workflow import ReminderWorkflow


def main() -> None:
    settings = load_settings()
    client = JiraClient(settings)

    try:
        issues = client.fetch_overdue_issues()
    except JiraClientError as exc:
        print(f"❌ Jira connection FAILED: {exc}")
        sys.exit(1)

    grouped = ReminderWorkflow._group_by_assignee(issues)

    print(f"Found {len(issues)} overdue issue(s) across {len(grouped)} assignee(s):\n")
    for assignee_email, assignee_issues in grouped.items():
        name = assignee_issues[0].assignee_display_name
        print(f"=== {name} <{assignee_email}> — {len(assignee_issues)} task(s) ===")
        for issue in assignee_issues:
            print(f"  - {issue.jira_key}: {issue.summary} (due {issue.due_date})")
        print()


if __name__ == "__main__":
    main()
