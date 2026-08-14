from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class TimesheetEntry(BaseModel):
    model_config = ConfigDict(frozen=True)

    entry_id: str = Field(min_length=1)
    assigned_to: str | None = None
    project_name: str | None = None
    summary: str | None = None
    note: str | None = None
    completed_date: date | None = None
    actual_start: datetime | None = None
    actual_finish: datetime | None = None
    actual_duration_hours: float | None = Field(default=None, ge=0)
    state: str | None = None
    employee: str = Field(min_length=1)
    work_date: date
    project: str = Field(min_length=1)
    task: str = Field(min_length=1)
    task_key: str = Field(min_length=1)
    hours: float = Field(ge=0)
    source_file: str = Field(min_length=1)
    source_hash: str = Field(min_length=1)
    source_sheet: str | None = None
    source_row: int | None = Field(default=None, ge=1)
    extra_fields_json: str | None = None


class ImportRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int | None = None
    source_file: str = Field(min_length=1)
    source_hash: str = Field(min_length=1)
    imported_at: datetime
    row_count: int = Field(ge=0)
    status: str = Field(min_length=1)


class DatasetSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    row_count: int = Field(ge=0)
    employee_count: int = Field(ge=0)
    project_count: int = Field(ge=0)
    task_count: int = Field(ge=0)
    state_count: int = Field(ge=0)
    total_hours: float = Field(ge=0)
    start_date: date | None = None
    end_date: date | None = None


class GraphStrategy(StrEnum):
    SEQUENTIAL = "SEQUENTIAL"
    ALL_TO_ALL = "ALL_TO_ALL"
