from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from src.quality.timesheet_quality import find_overlap_pairs, prepare_quality_dataframe, writing_quality


ESSENTIAL_COLUMNS = ("employee", "project", "task", "work_date", "hours")


@dataclass(frozen=True)
class DatasetReadiness:
    row_count: int
    required_columns_complete: bool
    missing_required_columns: tuple[str, ...]
    invalid_work_dates: int
    missing_essential_values: int
    minimal_note_count: int
    overlap_pair_count: int
    timed_entry_count: int
    timed_entry_coverage: float

    @property
    def is_ready(self) -> bool:
        return (
            self.required_columns_complete
            and self.invalid_work_dates == 0
            and self.missing_essential_values == 0
            and self.row_count > 0
        )


def build_dataset_readiness(dataframe: pd.DataFrame) -> DatasetReadiness:
    """Build lightweight deterministic readiness indicators for the active dataset.

    Readiness only blocks on structural/data-integrity issues. Note quality and time
    overlap are attention signals that should be reviewed in Audit Kualitas, not
    reasons to reject an otherwise valid dataset.
    """
    if dataframe.empty:
        return DatasetReadiness(
            row_count=0,
            required_columns_complete=False,
            missing_required_columns=ESSENTIAL_COLUMNS,
            invalid_work_dates=0,
            missing_essential_values=0,
            minimal_note_count=0,
            overlap_pair_count=0,
            timed_entry_count=0,
            timed_entry_coverage=0.0,
        )

    missing_columns = tuple(column for column in ESSENTIAL_COLUMNS if column not in dataframe.columns)
    required_columns_complete = not missing_columns

    invalid_work_dates = 0
    missing_essential_values = 0
    if required_columns_complete:
        work_dates = pd.to_datetime(dataframe["work_date"], errors="coerce")
        invalid_work_dates = int(work_dates.isna().sum())

        text_columns = ["employee", "project", "task"]
        text_missing = pd.Series(False, index=dataframe.index)
        for column in text_columns:
            values = dataframe[column].fillna("").astype(str).str.strip()
            text_missing |= values.eq("")

        hours = pd.to_numeric(dataframe["hours"], errors="coerce")
        invalid_hours = hours.isna() | (hours < 0)
        missing_essential_values = int((text_missing | work_dates.isna() | invalid_hours).sum())

    minimal_note_count = 0
    overlap_pair_count = 0
    timed_entry_count = 0
    timed_entry_coverage = 0.0

    quality_columns = {"employee", "project", "task", "note", "hours", "work_date", "actual_start", "actual_finish"}
    if quality_columns.issubset(dataframe.columns):
        prepared = prepare_quality_dataframe(dataframe)
        writing = writing_quality(prepared)
        minimal_note_count = int((writing["Kategori"] == "Minim").sum()) if not writing.empty else 0

        timed_mask = prepared["actual_start"].notna() & prepared["actual_finish"].notna()
        timed_entry_count = int(timed_mask.sum())
        timed_entry_coverage = float(timed_entry_count / len(prepared)) if len(prepared) else 0.0
        overlap_pair_count = int(len(find_overlap_pairs(prepared)))

    return DatasetReadiness(
        row_count=int(len(dataframe)),
        required_columns_complete=required_columns_complete,
        missing_required_columns=missing_columns,
        invalid_work_dates=invalid_work_dates,
        missing_essential_values=missing_essential_values,
        minimal_note_count=minimal_note_count,
        overlap_pair_count=overlap_pair_count,
        timed_entry_count=timed_entry_count,
        timed_entry_coverage=timed_entry_coverage,
    )
