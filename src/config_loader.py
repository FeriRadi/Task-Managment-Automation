"""Central configuration loading.

Combines two sources, on purpose kept separate:

* ``.env``            -> secrets / environment-specific values (Jira token, etc.)
* ``config/config.yaml`` -> everything else that is safe to version-control.

Nothing in this project should read `os.environ` or open the YAML file
directly outside of this module; every other module receives an already
validated :class:`Settings` instance (dependency injection).
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field


class JiraConfig(BaseModel):
    jql: str
    fields: list[str]
    request_timeout_seconds: int = 30
    max_results: int = 200
    verify_ssl: bool = True


class OutlookConfig(BaseModel):
    send_from_account: str = ""
    inbox_folder_name: str = "Inbox"
    reply_lookback_days: int = 7
    send_delay_seconds: int = 2


class EmailConfig(BaseModel):
    subject_prefix: str
    reminder_id_prefix: str
    template_file: str
    sender_display_name: str


class ScheduleConfig(BaseModel):
    send_reminders_day: str
    send_reminders_time: str
    process_replies_day: str
    process_replies_time: str


class DatabaseConfig(BaseModel):
    path: str
    schema_file: str
    busy_timeout_ms: int = 5000


class ReportsConfig(BaseModel):
    output_folder: str
    formats: list[str]
    filename_prefix: str


class LoggingConfig(BaseModel):
    level: str = "INFO"
    log_folder: str = "logs"
    log_file: str = "app.log"
    max_bytes: int = 5_242_880
    backup_count: int = 10
    format: str = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"


class ValidationConfig(BaseModel):
    allowed_statuses: list[str]
    date_format: str = "%Y-%m-%d"


class Settings(BaseModel):
    """Fully resolved application settings, combining YAML + environment."""

    project_root: Path
    jira_base_url: str
    jira_username: str
    jira_api_token: str
    jira_reporter: str

    jira: JiraConfig
    outlook: OutlookConfig
    email: EmailConfig
    schedule: ScheduleConfig
    database: DatabaseConfig
    reports: ReportsConfig
    logging: LoggingConfig
    validation: ValidationConfig

    def resolve_path(self, relative: str) -> Path:
        """Resolve a config-relative path against the project root."""
        return self.project_root / relative


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(
            f"Required environment variable '{name}' is missing. "
            f"Copy .env.example to .env and fill in the values."
        )
    return value


@lru_cache(maxsize=1)
def load_settings(project_root: str | Path | None = None) -> Settings:
    """Load and validate settings once per process.

    Parameters
    ----------
    project_root:
        Root directory of the project. Defaults to two levels up from this
        file (i.e. the repository root), which is correct when running
        ``main.py`` from the project root.
    """
    root = Path(project_root) if project_root else Path(__file__).resolve().parent.parent
    load_dotenv(root / ".env")

    config_path_env = os.environ.get("APP_CONFIG_PATH", "config/config.yaml")
    config_path = root / config_path_env
    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    with config_path.open("r", encoding="utf-8") as f:
        raw: dict[str, Any] = yaml.safe_load(f)

    return Settings(
        project_root=root,
        jira_base_url=_require_env("JIRA_BASE_URL"),
        jira_username=_require_env("JIRA_USERNAME"),
        jira_api_token=_require_env("JIRA_API_TOKEN"),
        jira_reporter=_require_env("JIRA_REPORTER"),
        jira=JiraConfig(**raw["jira"]),
        outlook=OutlookConfig(**raw["outlook"]),
        email=EmailConfig(**raw["email"]),
        schedule=ScheduleConfig(**raw["schedule"]),
        database=DatabaseConfig(**raw["database"]),
        reports=ReportsConfig(**raw["reports"]),
        logging=LoggingConfig(**raw["logging"]),
        validation=ValidationConfig(**raw["validation"]),
    )
