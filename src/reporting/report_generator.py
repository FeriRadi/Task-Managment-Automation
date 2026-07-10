"""Generates HTML, Excel, and CSV reports from the database's report rows.

Kept intentionally simple (pandas does the heavy lifting) so new report
formats can be added by extending ``FORMAT_WRITERS`` without touching
calling code.
"""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

import pandas as pd

from src.config_loader import Settings
from src.storage.database import Database

logger = logging.getLogger(__name__)

REPORT_COLUMNS = [
    "employee",
    "jira_key",
    "summary",
    "due_date",
    "reported_status",
    "requested_due_date",
    "comment",
    "reply_received",
    "reply_time",
]


class ReportGenerator:
    """Builds a pandas DataFrame from the database and writes it out in
    one or more configured formats."""

    def __init__(self, settings: Settings, database: Database) -> None:
        self._settings = settings
        self._database = database

    def _build_dataframe(self) -> pd.DataFrame:
        rows = self._database.fetch_report_rows()
        if not rows:
            return pd.DataFrame(columns=REPORT_COLUMNS)
        df = pd.DataFrame([dict(row) for row in rows])
        for col in REPORT_COLUMNS:
            if col not in df.columns:
                df[col] = None
        return df[REPORT_COLUMNS]

    def generate_all(self) -> list[Path]:
        """Generate every configured report format and return the list of
        written file paths."""
        df = self._build_dataframe()
        output_folder = self._settings.resolve_path(self._settings.reports.output_folder)
        output_folder.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_name = f"{self._settings.reports.filename_prefix}_{timestamp}"

        written: list[Path] = []
        for fmt in self._settings.reports.formats:
            writer = _FORMAT_WRITERS.get(fmt.lower())
            if writer is None:
                logger.warning("Unknown report format '%s' - skipping", fmt)
                continue
            path = output_folder / f"{base_name}.{fmt.lower()}"
            writer(df, path)
            logger.info("Wrote %s report to %s", fmt.upper(), path)
            written.append(path)
        return written


def _write_csv(df: pd.DataFrame, path: Path) -> None:
    df.to_csv(path, index=False)


def _write_xlsx(df: pd.DataFrame, path: Path) -> None:
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Reminder Report")


def _write_html(df: pd.DataFrame, path: Path) -> None:
    html_table = df.to_html(index=False, na_rep="", classes="reminder-report", border=0)
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Jira Reminder Report</title>
<style>
    body {{ font-family: Segoe UI, Arial, sans-serif; font-size: 13px; color: #222; }}
    table.reminder-report {{ border-collapse: collapse; width: 100%; }}
    table.reminder-report th, table.reminder-report td {{
        border: 1px solid #ccc; padding: 6px 10px; text-align: left;
    }}
    table.reminder-report th {{ background-color: #0b5394; color: #fff; }}
    table.reminder-report tr:nth-child(even) {{ background-color: #f5f7fa; }}
</style>
</head>
<body>
<h2>Jira Reminder Report</h2>
<p>Generated: {datetime.now().isoformat(sep=" ", timespec="seconds")}</p>
{html_table}
</body>
</html>"""
    path.write_text(html, encoding="utf-8")


_FORMAT_WRITERS = {
    "csv": _write_csv,
    "xlsx": _write_xlsx,
    "html": _write_html,
}
