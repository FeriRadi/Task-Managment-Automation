"""STEP 1 - Test the Jira connection only.

Run this first. It does NOT touch Outlook or the database. It just
proves that your .env credentials and JQL can reach Jira and return
something sensible.

Run from the project root:
    python scripts/step1_test_jira_connection.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config_loader import load_settings
from src.jira.client import JiraClient, JiraClientError


def main() -> None:
    print("Loading settings from .env and config/config.yaml ...")
    settings = load_settings()

    print(f"Jira base URL : {settings.jira_base_url}")
    print(f"Jira user     : {settings.jira_username}")
    print(f"JQL template  : {settings.jira.jql}")
    print()

    client = JiraClient(settings)

    try:
        issues = client.fetch_overdue_issues()
    except JiraClientError as exc:
        print(f"❌ Jira connection FAILED: {exc}")
        sys.exit(1)

    print(f"✅ Connected to Jira successfully. Found {len(issues)} overdue issue(s).\n")
    for issue in issues:
        print(f"  {issue.jira_key:10s} | {issue.status:12s} | due {issue.due_date} "
              f"| {issue.assignee_display_name} <{issue.assignee_email}>")
        print(f"             {issue.summary}")


if __name__ == "__main__":
    main()
