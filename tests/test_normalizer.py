from __future__ import annotations

import pandas as pd
import pytest

from src.ingestion.normalizer import (
    NormalizationError,
    build_task_key,
    normalize_timesheet_data,
    parse_hours,
    parse_work_date,
)


def test_task_key_generation() -> None:
    assert build_task_key(" FORCA ERP ", "  Fix Purchase Order ") == "forca erp::fix purchase order"


def test_date_conversion() -> None:
    parsed = parse_work_date("08/01/2026", 2)
    assert parsed.isoformat() == "2026-08-01"


def test_numeric_hours() -> None:
    assert parse_hours("3.5", 2) == 3.5


def test_whitespace_cleanup_and_zero_hour_warning() -> None:
    dataframe = pd.DataFrame(
        [
            {
                "employee": "  Ari   W ",
                "date": "2026-08-01",
                "project": " FORCA   ERP ",
                "task": " Fix   Purchase Order ",
                "hours": 0,
            }
        ]
    )
    entries, warnings = normalize_timesheet_data(dataframe, "sample.csv", "hash")
    assert entries[0].employee == "Ari W"
    assert entries[0].project == "FORCA ERP"
    assert entries[0].task == "Fix Purchase Order"
    assert warnings == ["Row 2: zero hours recorded"]


def test_invalid_date_raises() -> None:
    with pytest.raises(NormalizationError):
        parse_work_date("not-a-date", 2)
