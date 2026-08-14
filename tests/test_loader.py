from __future__ import annotations

from io import BytesIO

import pandas as pd
import pytest

from src.ingestion.loader import UnsupportedFileTypeError, load_timesheet_file


def test_load_valid_csv() -> None:
    content = b"employee,date,project,task,hours\nAri,2026-08-01,FORCA ERP,Fix PO,3\n"
    dataframe = load_timesheet_file("sample.csv", content)
    assert list(dataframe.columns) == ["employee", "date", "project", "task", "hours"]
    assert len(dataframe) == 1


def test_load_valid_xlsx() -> None:
    dataframe = pd.DataFrame(
        [{"employee": "Ari", "date": "2026-08-01", "project": "FORCA ERP", "task": "Fix PO", "hours": 3}]
    )
    buffer = BytesIO()
    dataframe.to_excel(buffer, index=False, engine="openpyxl")
    loaded = load_timesheet_file("sample.xlsx", buffer.getvalue())
    assert loaded.iloc[0]["employee"] == "Ari"


def test_load_excel_template_preserves_source_sheet() -> None:
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
            }
        ]
    )
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        dataframe.to_excel(writer, sheet_name="Sheet1", index=False)
    loaded = load_timesheet_file("mail.activity-7.xlsx", buffer.getvalue())
    assert loaded.attrs["source_sheet"] == "Sheet1"
    assert "Assigned to" in loaded.columns


def test_load_unsupported_file_type() -> None:
    with pytest.raises(UnsupportedFileTypeError):
        load_timesheet_file("sample.txt", b"hello")
