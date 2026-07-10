from datetime import date

import pytest

from src.utils.id_generator import generate_reminder_id


def test_generate_reminder_id_format():
    result = generate_reminder_id("REM", 1, run_date=date(2026, 7, 11))
    assert result == "REM-20260711-001"


def test_generate_reminder_id_pads_sequence():
    result = generate_reminder_id("REM", 42, run_date=date(2026, 7, 11))
    assert result == "REM-20260711-042"


def test_generate_reminder_id_rejects_non_positive_sequence():
    with pytest.raises(ValueError):
        generate_reminder_id("REM", 0)
