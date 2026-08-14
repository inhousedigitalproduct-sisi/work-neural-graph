from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from src.graph.builder import GraphFilterConfig, apply_graph_filters
from src.ingestion.mapper import detect_template_columns, normalize_template_headers
from src.ingestion.normalizer import normalize_template_timesheet_data
from src.ingestion.validator import validate_template_dataframe
from src.services import ImportService


def build_template_dataframe() -> pd.DataFrame:
    dataframe = pd.DataFrame(
        [
            {
                "Assigned to": "Budi Darmanto",
                "Project Name": "Product Development Periode 2026",
                "Summary": "DSUM dengan tim prodev",
                "Note": "DSUM dengan tim prodev",
                "Completed Date": "2026-08-12",
                "Actual Start": "2026-08-12 17:01:00",
                "Actual Finish": "2026-08-12 17:02:00",
                "Actual Duration (Hours)": 0.01666666666666667,
                "State": "Done",
                "Future Extra": "keep me",
            },
            {
                "Assigned to": "Ari",
                "Project Name": "FORCA ERP",
                "Summary": "Fallback work date task",
                "Note": "uses completed date",
                "Completed Date": "2026-08-11",
                "Actual Start": None,
                "Actual Finish": "2026-08-11 09:30:00",
                "Actual Duration (Hours)": 1.25,
                "State": "In Progress",
                "Future Extra": "keep me too",
            },
        ]
    )
    dataframe.attrs["source_sheet"] = "Sheet1"
    return dataframe


def test_all_nine_headers_recognized() -> None:
    template_info = detect_template_columns(build_template_dataframe().columns.tolist())
    assert template_info["recognized_count"] == 9
    assert template_info["missing_required"] == []
    assert template_info["extra_columns"] == ["Future Extra"]


def test_all_nine_values_preserved_and_aliases_derived() -> None:
    normalized, _ = normalize_template_headers(build_template_dataframe())
    entries, warnings = normalize_template_timesheet_data(normalized, "mail.activity-7.xlsx", "hash")
    entry = entries[0]
    assert entry.assigned_to == "Budi Darmanto"
    assert entry.project_name == "Product Development Periode 2026"
    assert entry.summary == "DSUM dengan tim prodev"
    assert entry.note == "DSUM dengan tim prodev"
    assert entry.completed_date == date(2026, 8, 12)
    assert entry.actual_start == datetime(2026, 8, 12, 17, 1, 0)
    assert entry.actual_finish == datetime(2026, 8, 12, 17, 2, 0)
    assert entry.actual_duration_hours == 0.01666666666666667
    assert entry.state == "Done"
    assert entry.employee == "Budi Darmanto"
    assert entry.project == "Product Development Periode 2026"
    assert entry.task == "DSUM dengan tim prodev"
    assert entry.hours == 0.01666666666666667
    assert entry.work_date == date(2026, 8, 12)
    assert entry.task_key == "product development periode 2026::dsum dengan tim prodev"
    assert entry.source_sheet == "Sheet1"
    assert entry.source_row == 2
    assert json.loads(entry.extra_fields_json or "{}")["Future Extra"] == "keep me"
    assert warnings


def test_work_date_fallbacks_to_completed_date() -> None:
    normalized, _ = normalize_template_headers(build_template_dataframe())
    entries, _ = normalize_template_timesheet_data(normalized, "mail.activity-7.xlsx", "hash")
    entry = entries[1]
    assert entry.actual_start is None
    assert entry.work_date == date(2026, 8, 11)


def test_state_and_note_preserved() -> None:
    normalized, _ = normalize_template_headers(build_template_dataframe())
    entries, _ = normalize_template_timesheet_data(normalized, "mail.activity-7.xlsx", "hash")
    assert entries[1].state == "In Progress"
    assert entries[1].note == "uses completed date"


def test_missing_required_column_produces_clear_error() -> None:
    dataframe = build_template_dataframe().drop(columns=["State"])
    result = validate_template_dataframe(dataframe)
    assert not result.is_valid
    assert "Missing required Excel template columns: State" in result.errors[0]


def test_extra_future_column_does_not_fail_import() -> None:
    normalized, _ = normalize_template_headers(build_template_dataframe())
    entries, warnings = normalize_template_timesheet_data(normalized, "mail.activity-7.xlsx", "hash")
    assert len(entries) == 2
    assert any("Additional template columns were preserved" in warning for warning in warnings)


def test_import_service_detects_and_prepares_template() -> None:
    service = ImportService(Path("data/test.db"))
    template_info = service.detect_import_mode(build_template_dataframe())
    assert template_info["is_template_candidate"] is True
    normalized, warnings = service.prepare_template_dataframe(build_template_dataframe())
    assert "assigned_to" in normalized.columns
    assert warnings


def test_state_and_note_filters_apply() -> None:
    normalized, _ = normalize_template_headers(build_template_dataframe())
    entries, _ = normalize_template_timesheet_data(normalized, "mail.activity-7.xlsx", "hash")
    dataframe = pd.DataFrame([entry.model_dump(mode="json") for entry in entries])
    filtered = apply_graph_filters(
        dataframe,
        GraphFilterConfig(states=("Done",), note_keyword="prodev"),
    )
    assert len(filtered) == 1
    assert filtered.iloc[0]["state"] == "Done"
