"""Structured, rotating-file logging setup.

Call :func:`configure_logging` once at application startup (from
``main.py``). Every module then just does ``logging.getLogger(__name__)``.
"""
from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path

from src.config_loader import Settings


def configure_logging(settings: Settings) -> None:
    """Configure the root logger with console + rotating file handlers."""
    log_folder = settings.resolve_path(settings.logging.log_folder)
    log_folder.mkdir(parents=True, exist_ok=True)
    log_file = log_folder / settings.logging.log_file

    root_logger = logging.getLogger()
    root_logger.setLevel(settings.logging.level.upper())

    # Avoid duplicate handlers if configure_logging is called more than once
    # (e.g. in tests).
    root_logger.handlers.clear()

    formatter = logging.Formatter(settings.logging.format)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(settings.logging.level.upper())
    root_logger.addHandler(console_handler)

    file_handler = logging.handlers.RotatingFileHandler(
        filename=str(log_file),
        maxBytes=settings.logging.max_bytes,
        backupCount=settings.logging.backup_count,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.DEBUG)
    root_logger.addHandler(file_handler)

    logging.getLogger(__name__).debug("Logging configured. Log file: %s", log_file)
