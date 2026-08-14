from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pandas as pd


class UnsupportedFileTypeError(ValueError):
    pass


def load_timesheet_file(file_name: str, content: bytes) -> pd.DataFrame:
    suffix = Path(file_name).suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(BytesIO(content))
    if suffix in {".xlsx", ".xlsm", ".xltx", ".xltm"}:
        excel_file = pd.ExcelFile(BytesIO(content), engine="openpyxl")
        sheet_name = excel_file.sheet_names[0]
        dataframe = pd.read_excel(excel_file, sheet_name=sheet_name)
        dataframe.attrs["source_sheet"] = sheet_name
        return dataframe
    raise UnsupportedFileTypeError(f"Unsupported file type: {suffix or 'unknown'}")
