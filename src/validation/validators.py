"""Validation rules applied to parsed replies before they are persisted.

Kept separate from parsing itself: the parser's job is to extract
structure; this module's job is to judge whether the extracted data makes
sense (known Jira key, allowed status, valid date, etc.).
"""
from __future__ import annotations

from datetime import datetime

from src.config_loader import Settings
from src.models.domain import ParsedUpdate


def validate_update(
    update: ParsedUpdate,
    known_jira_keys: set[str],
    settings: Settings,
) -> ParsedUpdate:
    """Return a new :class:`ParsedUpdate` with ``is_valid`` and
    ``validation_warnings`` populated.

    Parameters
    ----------
    update:
        The raw parsed update (as produced by the reply parser).
    known_jira_keys:
        Set of Jira keys that were actually included in the reminder
        email this reply is responding to (or, at minimum, keys known to
        the system). Used to flag replies about tasks we never asked
        about.
    settings:
        Application settings, for the allowed-status list and date format.
    """
    warnings: list[str] = []

    if update.jira_key not in known_jira_keys:
        warnings.append(f"Jira key '{update.jira_key}' was not part of the original reminder")

    if not update.status:
        warnings.append("Missing Status value")
    elif update.status not in settings.validation.allowed_statuses:
        warnings.append(
            f"Status '{update.status}' is not one of the allowed values: "
            f"{settings.validation.allowed_statuses}"
        )

    if update.requested_due_date:
        if not _is_valid_date(update.requested_due_date, settings.validation.date_format):
            warnings.append(
                f"Requested Due Date '{update.requested_due_date}' does not match "
                f"expected format {settings.validation.date_format}"
            )

    if update.status == "Blocked" and not update.requested_due_date:
        warnings.append("Status is 'Blocked' but no Requested Due Date was provided")

    return update.model_copy(update={"is_valid": len(warnings) == 0, "validation_warnings": warnings})


def _is_valid_date(value: str, date_format: str) -> bool:
    try:
        datetime.strptime(value, date_format)
        return True
    except ValueError:
        return False


def detect_duplicate_reply(entry_id: str, existing_entry_ids: set[str]) -> bool:
    """Return True if this Outlook message has already been processed."""
    return entry_id in existing_entry_ids
