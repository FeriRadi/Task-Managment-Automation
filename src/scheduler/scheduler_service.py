"""Weekly scheduler: Saturday-morning reminders, Saturday-afternoon reply
processing. Built on the lightweight ``schedule`` library rather than a
full task queue, since the cadence is a simple weekly job.
"""
from __future__ import annotations

import logging
import time

import schedule

from src.config_loader import Settings
from src.workflow import ReminderWorkflow

logger = logging.getLogger(__name__)

_DAY_METHODS = {
    "monday": schedule.every().monday,
    "tuesday": schedule.every().tuesday,
    "wednesday": schedule.every().wednesday,
    "thursday": schedule.every().thursday,
    "friday": schedule.every().friday,
    "saturday": schedule.every().saturday,
    "sunday": schedule.every().sunday,
}


def _safe_run(job_name: str, func) -> None:
    try:
        logger.info("Starting scheduled job: %s", job_name)
        func()
        logger.info("Finished scheduled job: %s", job_name)
    except Exception:
        logger.exception("Scheduled job '%s' failed", job_name)


def build_schedule(settings: Settings, workflow: ReminderWorkflow) -> None:
    """Register the two weekly jobs against the ``schedule`` module's
    global scheduler."""
    send_day = settings.schedule.send_reminders_day.lower()
    process_day = settings.schedule.process_replies_day.lower()

    if send_day not in _DAY_METHODS or process_day not in _DAY_METHODS:
        raise ValueError("schedule.*_day config values must be full lowercase weekday names")

    _DAY_METHODS[send_day].at(settings.schedule.send_reminders_time).do(
        _safe_run, "send_reminders", workflow.send_reminders
    )
    _DAY_METHODS[process_day].at(settings.schedule.process_replies_time).do(
        _safe_run, "process_replies", workflow.process_replies
    )

    logger.info(
        "Scheduled 'send_reminders' every %s at %s, 'process_replies' every %s at %s",
        send_day, settings.schedule.send_reminders_time,
        process_day, settings.schedule.process_replies_time,
    )


def run_forever(poll_interval_seconds: int = 30) -> None:
    """Block forever, running any due jobs. Intended to be run as a
    long-lived background process (e.g. via Windows Task Scheduler
    keeping the process alive, or a simple `python main.py schedule`
    left running)."""
    logger.info("Scheduler loop started (poll interval: %ss)", poll_interval_seconds)
    while True:
        schedule.run_pending()
        time.sleep(poll_interval_seconds)
