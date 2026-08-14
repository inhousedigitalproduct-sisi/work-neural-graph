from __future__ import annotations

from datetime import date, datetime

import pytest

from src.database.repository import DuplicateImportError, TimesheetRepository
from src.domain.models import TimesheetEntry


def build_entry(source_hash: str = "hash") -> TimesheetEntry:
    return TimesheetEntry(
        entry_id="entry-1",
        assigned_to="Ari",
        project_name="FORCA ERP",
        summary="Fix PO",
        note="Investigate supplier path",
        completed_date=date(2026, 8, 1),
        actual_start=datetime(2026, 8, 1, 9, 0, 0),
        actual_finish=datetime(2026, 8, 1, 12, 0, 0),
        actual_duration_hours=3.0,
        state="Done",
        employee="Ari",
        work_date=date(2026, 8, 1),
        project="FORCA ERP",
        task="Fix PO",
        task_key="forca erp::fix po",
        hours=3.0,
        source_file="sample.csv",
        source_hash=source_hash,
        source_sheet="Sheet1",
        source_row=2,
        extra_fields_json='{"Future Extra":"keep"}',
    )


def test_database_initialization(temp_db_path) -> None:
    repository = TimesheetRepository(temp_db_path)
    assert repository.load_timesheet_entries() == []


def test_successful_import_and_load_entries(temp_db_path) -> None:
    repository = TimesheetRepository(temp_db_path)
    repository.save_import_with_entries("sample.csv", "hash", [build_entry()])
    entries = repository.load_timesheet_entries()
    assert len(entries) == 1
    assert entries[0].employee == "Ari"


def test_duplicate_import_detection(temp_db_path) -> None:
    repository = TimesheetRepository(temp_db_path)
    repository.save_import_with_entries("sample.csv", "hash", [build_entry()])
    with pytest.raises(DuplicateImportError):
        repository.save_import_with_entries("sample.csv", "hash", [build_entry()])


def test_load_normalized_entries(temp_db_path) -> None:
    repository = TimesheetRepository(temp_db_path)
    repository.save_import_with_entries("sample.csv", "hash", [build_entry()])
    loaded = repository.load_timesheet_entries()
    assert loaded[0].task_key == "forca erp::fix po"
    assert loaded[0].state == "Done"
    assert loaded[0].note == "Investigate supplier path"
