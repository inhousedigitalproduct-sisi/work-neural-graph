from __future__ import annotations

import json
from datetime import date, datetime

import pandas as pd

from src.domain.models import TimesheetEntry
from src.ingestion.mapper import TEMPLATE_FIELD_ALIASES
from src.utils.hashing import sha256_bytes


class NormalizationError(ValueError):
    pass


def clean_text(value: object) -> str:
    text = " ".join(str(value).split()).strip()
    return text


def normalize_for_key(value: object) -> str:
    return clean_text(value).lower()


def build_task_key(project: object, task: object) -> str:
    return f"{normalize_for_key(project)}::{normalize_for_key(task)}"


def parse_work_date(value: object, row_number: int) -> date:
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        raise NormalizationError(f"Row {row_number}: invalid date '{value}'")
    return parsed.date()


def parse_optional_date(value: object) -> date | None:
    if pd.isna(value) or value is None or clean_text(value) == "":
        return None
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.date()


def parse_optional_datetime(value: object) -> datetime | None:
    if pd.isna(value) or value is None or clean_text(value) == "":
        return None
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.to_pydatetime()


def parse_hours(value: object, row_number: int) -> float:
    try:
        hours = float(value)
    except (TypeError, ValueError) as exc:
        raise NormalizationError(f"Row {row_number}: invalid hours '{value}'") from exc
    if hours < 0:
        raise NormalizationError(f"Row {row_number}: negative hours are not allowed")
    return hours


def validate_non_empty(field_name: str, value: object, row_number: int) -> str:
    cleaned = clean_text(value)
    if not cleaned:
        raise NormalizationError(f"Row {row_number}: {field_name} cannot be empty")
    return cleaned


def build_entry_id(
    employee: str,
    work_date: date,
    project: str,
    task: str,
    hours: float,
    source_hash: str,
    source_row_number: int,
) -> str:
    raw = "|".join(
        [
            employee,
            work_date.isoformat(),
            project,
            task,
            f"{hours:.4f}",
            source_hash,
            str(source_row_number),
        ]
    )
    return sha256_bytes(raw.encode("utf-8"))


def normalize_timesheet_data(
    dataframe: pd.DataFrame,
    source_file: str,
    source_hash: str,
) -> tuple[list[TimesheetEntry], list[str]]:
    entries: list[TimesheetEntry] = []
    warnings: list[str] = []

    for index, row in dataframe.iterrows():
        row_number = index + 2
        employee = validate_non_empty("employee", row["employee"], row_number)
        project = validate_non_empty("project", row["project"], row_number)
        task = validate_non_empty("task", row["task"], row_number)
        work_date = parse_work_date(row["date"], row_number)
        hours = parse_hours(row["hours"], row_number)
        if hours == 0:
            warnings.append(f"Row {row_number}: zero hours recorded")

        entry = TimesheetEntry(
            entry_id=build_entry_id(
                employee=employee,
                work_date=work_date,
                project=project,
                task=task,
                hours=hours,
                source_hash=source_hash,
                source_row_number=row_number,
            ),
            employee=employee,
            work_date=work_date,
            project=project,
            task=task,
            task_key=build_task_key(project, task),
            hours=hours,
            source_file=source_file,
            source_hash=source_hash,
        )
        entries.append(entry)

    return entries, warnings


def derive_template_work_date(
    actual_start: datetime | None,
    completed_date: date | None,
    actual_finish: datetime | None,
    row_number: int,
) -> date:
    if actual_start is not None:
        return actual_start.date()
    if completed_date is not None:
        return completed_date
    if actual_finish is not None:
        return actual_finish.date()
    raise NormalizationError(
        f"Row {row_number}: unable to derive work_date; provide Actual Start, Completed Date, or Actual Finish"
    )


def normalize_template_timesheet_data(
    dataframe: pd.DataFrame,
    source_file: str,
    source_hash: str,
) -> tuple[list[TimesheetEntry], list[str]]:
    entries: list[TimesheetEntry] = []
    warnings: list[str] = []
    source_sheet = dataframe.attrs.get("source_sheet")
    template_info = dataframe.attrs.get("template_info", {})
    known_template_columns = set(TEMPLATE_FIELD_ALIASES.values())

    for index, row in dataframe.iterrows():
        row_number = index + 2
        assigned_to = validate_non_empty("assigned_to", row["assigned_to"], row_number)
        project_name = validate_non_empty("project_name", row["project_name"], row_number)
        summary = validate_non_empty("summary", row["summary"], row_number)
        state = validate_non_empty("state", row["state"], row_number)
        note = clean_text(row["note"]) if "note" in row and not pd.isna(row["note"]) else None
        note = note or None
        completed_date = parse_optional_date(row["completed_date"]) if "completed_date" in row else None
        actual_start = parse_optional_datetime(row["actual_start"]) if "actual_start" in row else None
        actual_finish = parse_optional_datetime(row["actual_finish"]) if "actual_finish" in row else None
        actual_duration_hours = parse_hours(row["actual_duration_hours"], row_number)
        work_date = derive_template_work_date(actual_start, completed_date, actual_finish, row_number)
        if actual_duration_hours == 0:
            warnings.append(f"Row {row_number}: zero hours recorded")

        extra_fields = {
            column: row[column]
            for column in dataframe.columns
            if column not in known_template_columns
        }
        extra_fields_json = None
        if extra_fields:
            serializable = {
                key: (
                    value.isoformat()
                    if isinstance(value, (pd.Timestamp, datetime))
                    else value.item()
                    if hasattr(value, "item")
                    else value
                )
                for key, value in extra_fields.items()
                if not pd.isna(value)
            }
            extra_fields_json = json.dumps(serializable, ensure_ascii=True, sort_keys=True) if serializable else None

        entry = TimesheetEntry(
            entry_id=build_entry_id(
                employee=assigned_to,
                work_date=work_date,
                project=project_name,
                task=summary,
                hours=actual_duration_hours,
                source_hash=source_hash,
                source_row_number=row_number,
            ),
            assigned_to=assigned_to,
            project_name=project_name,
            summary=summary,
            note=note,
            completed_date=completed_date,
            actual_start=actual_start,
            actual_finish=actual_finish,
            actual_duration_hours=actual_duration_hours,
            state=state,
            employee=assigned_to,
            work_date=work_date,
            project=project_name,
            task=summary,
            task_key=build_task_key(project_name, summary),
            hours=actual_duration_hours,
            source_file=source_file,
            source_hash=source_hash,
            source_sheet=source_sheet,
            source_row=row_number,
            extra_fields_json=extra_fields_json,
        )
        entries.append(entry)

    if template_info.get("extra_columns"):
        warnings.append(
            "Additional template columns were preserved as raw metadata: "
            + ", ".join(template_info["extra_columns"])
        )

    return entries, warnings
