"""Command-line entrypoint for the Jira Reminder / Outlook Reply Tracking
application.

Usage:
    python main.py init-db              Initialize the SQLite database schema
    python main.py send-reminders       Run the "send reminders" job once, now
    python main.py process-replies      Run the "process replies" job once, now
    python main.py generate-reports     Regenerate HTML/Excel/CSV reports
    python main.py run-scheduler        Start the long-running weekly scheduler
"""
from __future__ import annotations

import argparse
import logging
import sys

from src.config_loader import load_settings
from src.scheduler.scheduler_service import build_schedule, run_forever
from src.storage.database import Database, DatabaseError
from src.utils.logging_setup import configure_logging
from src.workflow import ReminderWorkflow

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Jira Reminder / Outlook Reply Tracking application"
    )
    parser.add_argument(
        "command",
        choices=[
            "init-db",
            "send-reminders",
            "process-replies",
            "generate-reports",
            "run-scheduler",
        ],
        help="Which action to run",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    settings = load_settings()
    configure_logging(settings)

    database = Database(settings)
    try:
        database.initialize_schema()
    except DatabaseError:
        logger.exception("Could not initialize the database")
        return 1

    if args.command == "init-db":
        logger.info("Database initialized. Nothing else to do.")
        return 0

    workflow = ReminderWorkflow(settings, database)

    if args.command == "send-reminders":
        count = workflow.send_reminders()
        logger.info("send-reminders complete: %d email(s) sent", count)
        return 0

    if args.command == "process-replies":
        count = workflow.process_replies()
        logger.info("process-replies complete: %d repl(y/ies) processed", count)
        return 0

    if args.command == "generate-reports":
        from src.reporting.report_generator import ReportGenerator

        paths = ReportGenerator(settings, database).generate_all()
        for path in paths:
            logger.info("Report written: %s", path)
        return 0

    if args.command == "run-scheduler":
        build_schedule(settings, workflow)
        run_forever()
        return 0  # pragma: no cover - unreachable, run_forever() blocks

    return 1  # pragma: no cover - argparse choices prevent this


if __name__ == "__main__":
    sys.exit(main())
