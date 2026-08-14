from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from src.database.sqlite import get_connection
from src.domain.models import ImportRecord, TimesheetEntry

logger = logging.getLogger(__name__)


class DuplicateImportError(ValueError):
    pass


class TimesheetRepository:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    def import_exists(self, source_hash: str) -> bool:
        with get_connection(self.db_path) as connection:
            row = connection.execute(
                "SELECT 1 FROM imports WHERE source_hash = ? AND status = 'SUCCESS'",
                (source_hash,),
            ).fetchone()
        return row is not None

    def save_import(self, source_file: str, source_hash: str, row_count: int, status: str) -> int:
        imported_at = datetime.now(timezone.utc).isoformat()
        with get_connection(self.db_path) as connection:
            cursor = connection.execute(
                """
                INSERT INTO imports (source_file, source_hash, imported_at, row_count, status)
                VALUES (?, ?, ?, ?, ?)
                """,
                (source_file, source_hash, imported_at, row_count, status),
            )
            return int(cursor.lastrowid)

    def save_timesheet_entries(self, entries: list[TimesheetEntry]) -> None:
        if not entries:
            return
        with get_connection(self.db_path) as connection:
            connection.executemany(
                """
                INSERT INTO timesheet_entries (
                    entry_id, assigned_to, project_name, summary, note, completed_date,
                    actual_start, actual_finish, actual_duration_hours, state,
                    employee, work_date, project, task, task_key,
                    hours, source_file, source_hash, source_sheet, source_row, extra_fields_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        entry.entry_id,
                        entry.assigned_to,
                        entry.project_name,
                        entry.summary,
                        entry.note,
                        entry.completed_date.isoformat() if entry.completed_date else None,
                        entry.actual_start.isoformat() if entry.actual_start else None,
                        entry.actual_finish.isoformat() if entry.actual_finish else None,
                        entry.actual_duration_hours,
                        entry.state,
                        entry.employee,
                        entry.work_date.isoformat(),
                        entry.project,
                        entry.task,
                        entry.task_key,
                        entry.hours,
                        entry.source_file,
                        entry.source_hash,
                        entry.source_sheet,
                        entry.source_row,
                        entry.extra_fields_json,
                    )
                    for entry in entries
                ],
            )

    def save_import_with_entries(
        self,
        source_file: str,
        source_hash: str,
        entries: list[TimesheetEntry],
    ) -> int:
        if self.import_exists(source_hash):
            logger.info("Duplicate import detected for hash %s", source_hash)
            raise DuplicateImportError("This file was already imported successfully.")

        with get_connection(self.db_path) as connection:
            try:
                logger.info("Saving import for %s", source_file)
                cursor = connection.execute(
                    """
                    INSERT INTO imports (source_file, source_hash, imported_at, row_count, status)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        source_file,
                        source_hash,
                        datetime.now(timezone.utc).isoformat(),
                        len(entries),
                        "SUCCESS",
                    ),
                )
                connection.executemany(
                    """
                    INSERT INTO timesheet_entries (
                        entry_id, assigned_to, project_name, summary, note, completed_date,
                        actual_start, actual_finish, actual_duration_hours, state,
                        employee, work_date, project, task, task_key,
                        hours, source_file, source_hash, source_sheet, source_row, extra_fields_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            entry.entry_id,
                            entry.assigned_to,
                            entry.project_name,
                            entry.summary,
                            entry.note,
                            entry.completed_date.isoformat() if entry.completed_date else None,
                            entry.actual_start.isoformat() if entry.actual_start else None,
                            entry.actual_finish.isoformat() if entry.actual_finish else None,
                            entry.actual_duration_hours,
                            entry.state,
                            entry.employee,
                            entry.work_date.isoformat(),
                            entry.project,
                            entry.task,
                            entry.task_key,
                            entry.hours,
                            entry.source_file,
                            entry.source_hash,
                            entry.source_sheet,
                            entry.source_row,
                            entry.extra_fields_json,
                        )
                        for entry in entries
                    ],
                )
                connection.commit()
            except Exception:
                connection.rollback()
                logger.exception("Failed to save import for %s", source_file)
                raise
        return int(cursor.lastrowid)

    def replace_dataset_with_import(
        self,
        source_file: str,
        source_hash: str,
        entries: list[TimesheetEntry],
    ) -> int:
        with get_connection(self.db_path) as connection:
            try:
                logger.info("Replacing dataset with import for %s", source_file)
                connection.execute("DELETE FROM timesheet_entries")
                connection.execute("DELETE FROM imports")
                cursor = connection.execute(
                    """
                    INSERT INTO imports (source_file, source_hash, imported_at, row_count, status)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        source_file,
                        source_hash,
                        datetime.now(timezone.utc).isoformat(),
                        len(entries),
                        "SUCCESS",
                    ),
                )
                connection.executemany(
                    """
                    INSERT INTO timesheet_entries (
                        entry_id, assigned_to, project_name, summary, note, completed_date,
                        actual_start, actual_finish, actual_duration_hours, state,
                        employee, work_date, project, task, task_key,
                        hours, source_file, source_hash, source_sheet, source_row, extra_fields_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            entry.entry_id,
                            entry.assigned_to,
                            entry.project_name,
                            entry.summary,
                            entry.note,
                            entry.completed_date.isoformat() if entry.completed_date else None,
                            entry.actual_start.isoformat() if entry.actual_start else None,
                            entry.actual_finish.isoformat() if entry.actual_finish else None,
                            entry.actual_duration_hours,
                            entry.state,
                            entry.employee,
                            entry.work_date.isoformat(),
                            entry.project,
                            entry.task,
                            entry.task_key,
                            entry.hours,
                            entry.source_file,
                            entry.source_hash,
                            entry.source_sheet,
                            entry.source_row,
                            entry.extra_fields_json,
                        )
                        for entry in entries
                    ],
                )
                connection.commit()
            except Exception:
                connection.rollback()
                logger.exception("Failed to replace dataset with import for %s", source_file)
                raise
        return int(cursor.lastrowid)

    def reset_dataset(self) -> None:
        with get_connection(self.db_path) as connection:
            try:
                logger.info("Resetting dataset")
                connection.execute("DELETE FROM timesheet_entries")
                connection.execute("DELETE FROM imports")
                connection.commit()
            except Exception:
                connection.rollback()
                logger.exception("Failed to reset dataset")
                raise

    def load_timesheet_entries(self) -> list[TimesheetEntry]:
        with get_connection(self.db_path) as connection:
            rows = connection.execute(
                """
                SELECT entry_id, assigned_to, project_name, summary, note, completed_date,
                       actual_start, actual_finish, actual_duration_hours, state,
                       employee, work_date, project, task, task_key,
                       hours, source_file, source_hash, source_sheet, source_row, extra_fields_json
                FROM timesheet_entries
                ORDER BY work_date, employee, project, task
                """
            ).fetchall()
        return [
            TimesheetEntry(
                entry_id=row["entry_id"],
                assigned_to=row["assigned_to"],
                project_name=row["project_name"],
                summary=row["summary"],
                note=row["note"],
                completed_date=datetime.fromisoformat(row["completed_date"]).date()
                if row["completed_date"]
                else None,
                actual_start=datetime.fromisoformat(row["actual_start"]) if row["actual_start"] else None,
                actual_finish=datetime.fromisoformat(row["actual_finish"]) if row["actual_finish"] else None,
                actual_duration_hours=row["actual_duration_hours"],
                state=row["state"],
                employee=row["employee"],
                work_date=datetime.fromisoformat(row["work_date"]).date(),
                project=row["project"],
                task=row["task"],
                task_key=row["task_key"],
                hours=row["hours"],
                source_file=row["source_file"],
                source_hash=row["source_hash"],
                source_sheet=row["source_sheet"],
                source_row=row["source_row"],
                extra_fields_json=row["extra_fields_json"],
            )
            for row in rows
        ]

    def load_imports(self) -> list[ImportRecord]:
        with get_connection(self.db_path) as connection:
            rows = connection.execute(
                """
                SELECT id, source_file, source_hash, imported_at, row_count, status
                FROM imports
                ORDER BY imported_at DESC
                """
            ).fetchall()
        return [
            ImportRecord(
                id=row["id"],
                source_file=row["source_file"],
                source_hash=row["source_hash"],
                imported_at=datetime.fromisoformat(row["imported_at"]),
                row_count=row["row_count"],
                status=row["status"],
            )
            for row in rows
        ]

    def get_latest_successful_import(self) -> ImportRecord | None:
        with get_connection(self.db_path) as connection:
            row = connection.execute(
                """
                SELECT id, source_file, source_hash, imported_at, row_count, status
                FROM imports
                WHERE status = 'SUCCESS'
                ORDER BY imported_at DESC
                LIMIT 1
                """
            ).fetchone()
        if row is None:
            return None
        return ImportRecord(
            id=row["id"],
            source_file=row["source_file"],
            source_hash=row["source_hash"],
            imported_at=datetime.fromisoformat(row["imported_at"]),
            row_count=row["row_count"],
            status=row["status"],
        )
