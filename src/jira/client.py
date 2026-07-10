"""Thin wrapper around the Jira REST API (Server / Data Center).

Only what this project needs: run a JQL search and return validated
:class:`JiraIssue` objects. No AI, no heuristics -- just the REST API.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any

import requests
from requests.auth import HTTPBasicAuth

from src.config_loader import Settings
from src.models.domain import JiraIssue

logger = logging.getLogger(__name__)


class JiraClientError(Exception):
    """Raised for any unrecoverable Jira communication failure."""


class JiraClient:
    """Minimal Jira REST client using JQL search.

    Parameters
    ----------
    settings:
        Fully loaded application settings (injected, not read globally).
    session:
        Optional pre-built ``requests.Session`` (mainly for testing).
    """

    SEARCH_ENDPOINT = "/rest/api/2/search"

    def __init__(self, settings: Settings, session: requests.Session | None = None) -> None:
        self._settings = settings
        self._session = session or requests.Session()
        self._session.auth = HTTPBasicAuth(settings.jira_username, settings.jira_api_token)
        self._session.headers.update({"Accept": "application/json"})

    def _build_jql(self) -> str:
        return self._settings.jira.jql.format(
            reporter=self._settings.jira_reporter,
            today=date.today().isoformat(),
        )

    def fetch_overdue_issues(self) -> list[JiraIssue]:
        """Run the configured JQL and return validated, overdue, unresolved
        issues assigned to a real person.

        Raises
        ------
        JiraClientError
            If the Jira server is unreachable, credentials are invalid, or
            the response cannot be parsed.
        """
        jql = self._build_jql()
        logger.info("Querying Jira with JQL: %s", jql)

        params: dict[str, Any] = {
            "jql": jql,
            "fields": ",".join(self._settings.jira.fields),
            "maxResults": self._settings.jira.max_results,
        }
        url = self._settings.jira_base_url.rstrip("/") + self.SEARCH_ENDPOINT

        try:
            response = self._session.get(
                url,
                params=params,
                timeout=self._settings.jira.request_timeout_seconds,
                verify=self._settings.jira.verify_ssl,
            )
        except requests.exceptions.ConnectionError as exc:
            raise JiraClientError(f"Could not connect to Jira at {url}") from exc
        except requests.exceptions.Timeout as exc:
            raise JiraClientError("Jira request timed out") from exc

        if response.status_code == 401:
            raise JiraClientError("Jira authentication failed - check credentials in .env")
        if response.status_code == 403:
            raise JiraClientError("Jira access forbidden - check permissions for this account")
        if not response.ok:
            raise JiraClientError(
                f"Jira search failed with HTTP {response.status_code}: {response.text[:500]}"
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise JiraClientError("Jira response was not valid JSON") from exc

        issues = payload.get("issues", [])
        logger.info("Jira returned %d overdue issue(s)", len(issues))

        return [self._to_jira_issue(raw) for raw in issues if self._has_assignee(raw)]

    @staticmethod
    def _has_assignee(raw_issue: dict[str, Any]) -> bool:
        has_assignee = bool(raw_issue.get("fields", {}).get("assignee"))
        if not has_assignee:
            logger.warning(
                "Skipping issue %s: no assignee set", raw_issue.get("key", "UNKNOWN")
            )
        return has_assignee

    @staticmethod
    def _to_jira_issue(raw_issue: dict[str, Any]) -> JiraIssue:
        fields = raw_issue.get("fields", {})
        assignee = fields.get("assignee") or {}
        status = fields.get("status") or {}

        return JiraIssue(
            jira_key=raw_issue["key"],
            summary=fields.get("summary", ""),
            due_date=fields.get("duedate"),
            assignee_email=assignee.get("emailAddress", ""),
            assignee_display_name=assignee.get("displayName", assignee.get("name", "Unknown")),
            status=status.get("name", "Unknown"),
            resolution=(fields.get("resolution") or {}).get("name"),
        )
