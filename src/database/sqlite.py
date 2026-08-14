from __future__ import annotations

import sqlite3
from pathlib import Path


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS imports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_file TEXT NOT NULL,
    source_hash TEXT NOT NULL UNIQUE,
    imported_at TEXT NOT NULL,
    row_count INTEGER NOT NULL,
    status TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS timesheet_entries (
    entry_id TEXT PRIMARY KEY,
    assigned_to TEXT,
    project_name TEXT,
    summary TEXT,
    note TEXT,
    completed_date TEXT,
    actual_start TEXT,
    actual_finish TEXT,
    actual_duration_hours REAL,
    state TEXT,
    employee TEXT NOT NULL,
    work_date TEXT NOT NULL,
    project TEXT NOT NULL,
    task TEXT NOT NULL,
    task_key TEXT NOT NULL,
    hours REAL NOT NULL,
    source_file TEXT NOT NULL,
    source_hash TEXT NOT NULL,
    source_sheet TEXT,
    source_row INTEGER,
    extra_fields_json TEXT,
    FOREIGN KEY (source_hash) REFERENCES imports (source_hash)
);

CREATE INDEX IF NOT EXISTS idx_timesheet_entries_work_date ON timesheet_entries(work_date);
CREATE INDEX IF NOT EXISTS idx_timesheet_entries_employee ON timesheet_entries(employee);
CREATE INDEX IF NOT EXISTS idx_timesheet_entries_project ON timesheet_entries(project);
CREATE INDEX IF NOT EXISTS idx_timesheet_entries_task_key ON timesheet_entries(task_key);
"""

TIMESHEET_ENTRY_MIGRATION_COLUMNS = {
    "assigned_to": "TEXT",
    "project_name": "TEXT",
    "summary": "TEXT",
    "note": "TEXT",
    "completed_date": "TEXT",
    "actual_start": "TEXT",
    "actual_finish": "TEXT",
    "actual_duration_hours": "REAL",
    "state": "TEXT",
    "source_sheet": "TEXT",
    "source_row": "INTEGER",
    "extra_fields_json": "TEXT",
}


def get_connection(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database(db_path: Path) -> None:
    with get_connection(db_path) as connection:
        connection.executescript(SCHEMA_SQL)
        existing_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(timesheet_entries)").fetchall()
        }
        for column_name, column_type in TIMESHEET_ENTRY_MIGRATION_COLUMNS.items():
            if column_name not in existing_columns:
                connection.execute(
                    f"ALTER TABLE timesheet_entries ADD COLUMN {column_name} {column_type}"
                )
