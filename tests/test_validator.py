from __future__ import annotations

import pandas as pd
import pytest

from src.ingestion.normalizer import NormalizationError, normalize_timesheet_data
from src.ingestion.validator import validate_required_fields


def test_missing_required_field() -> None:
    dataframe = pd.DataFrame([{"employee": "Ari", "date": "2026-08-01"}])
    result = validate_required_fields(dataframe)
    assert not result.is_valid
    assert "project" in result.errors[0]


def test_invalid_date() -> None:
    dataframe = pd.DataFrame(
        [{"employee": "Ari", "date": "bad", "project": "FORCA ERP", "task": "Fix PO", "hours": 2}]
    )
    with pytest.raises(NormalizationError):
        normalize_timesheet_data(dataframe, "sample.csv", "hash")


def test_negative_hours() -> None:
    dataframe = pd.DataFrame(
        [{"employee": "Ari", "date": "2026-08-01", "project": "FORCA ERP", "task": "Fix PO", "hours": -1}]
    )
    with pytest.raises(NormalizationError):
        normalize_timesheet_data(dataframe, "sample.csv", "hash")
