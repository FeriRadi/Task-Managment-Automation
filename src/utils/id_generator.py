"""Generation of unique, human-readable Reminder IDs.

Format: ``<PREFIX>-<YYYYMMDD>-<sequence>``, e.g. ``REM-20260711-001``.
The sequence is scoped to a single calendar day and is provided by the
caller (typically the count of reminders already sent today, from the
database) so IDs stay strictly increasing and collision-free even across
process restarts.
"""
from __future__ import annotations

from datetime import date


def generate_reminder_id(prefix: str, sequence: int, run_date: date | None = None) -> str:
    """Build a Reminder ID.

    Parameters
    ----------
    prefix:
        Short prefix, e.g. ``REM``.
    sequence:
        1-based sequence number for the day (e.g. the 3rd reminder sent
        today should pass ``sequence=3``).
    run_date:
        Date to embed; defaults to today.
    """
    if sequence < 1:
        raise ValueError("sequence must be a positive integer")
    effective_date = run_date or date.today()
    return f"{prefix}-{effective_date.strftime('%Y%m%d')}-{sequence:03d}"
