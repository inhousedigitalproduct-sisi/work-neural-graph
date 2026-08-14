from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd
import streamlit as st

from src.database.repository import DuplicateImportError, TimesheetRepository
from src.database.sqlite import initialize_database
from src.domain.models import DatasetSummary, GraphStrategy, TimesheetEntry
from src.graph.builder import (
    GraphBuildConfig,
    GraphBuildResult,
    GraphBuilder,
    GraphFilterConfig,
    apply_graph_filters,
)
from src.ingestion.loader import load_timesheet_file
from src.ingestion.mapper import detect_template_columns, normalize_template_headers, validate_mapping
from src.ingestion.normalizer import (
    NormalizationError,
    normalize_template_timesheet_data,
    normalize_timesheet_data,
)
from src.ingestion.validator import validate_required_fields, validate_template_dataframe
from src.utils.hashing import sha256_bytes

logger = logging.getLogger(__name__)


class ImportService:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        logger.info("ImportService using database path %s", self.db_path.resolve())
        initialize_database(self.db_path)
        self.repository = TimesheetRepository(self.db_path)

    def load_raw_file(self, file_name: str, content: bytes) -> pd.DataFrame:
        logger.info("Loading file %s", file_name)
        dataframe = load_timesheet_file(file_name, content)
        if dataframe.empty:
            raise ValueError("The uploaded file is empty.")
        return dataframe

    def detect_import_mode(self, dataframe: pd.DataFrame) -> dict[str, object]:
        return detect_template_columns(dataframe.columns.tolist())

    def apply_mapping(self, dataframe: pd.DataFrame, mapping: dict[str, str | None]) -> pd.DataFrame:
        mapping_errors = validate_mapping(mapping)
        if mapping_errors:
            raise ValueError("\n".join(mapping_errors))

        renamed = dataframe.rename(columns={source: logical for logical, source in mapping.items() if source})
        normalized = renamed[list(mapping.keys())].copy()
        validation_result = validate_required_fields(normalized)
        if not validation_result.is_valid:
            raise ValueError("\n".join(validation_result.errors))
        return normalized

    def prepare_template_dataframe(self, dataframe: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
        normalized, template_info = normalize_template_headers(dataframe)
        validation_result = validate_template_dataframe(dataframe)
        if not validation_result.is_valid:
            raise ValueError("\n".join(validation_result.errors))
        return normalized, validation_result.warnings

    def normalize_entries(
        self,
        dataframe: pd.DataFrame,
        source_file: str,
        content: bytes,
    ) -> tuple[list[TimesheetEntry], list[str], str]:
        source_hash = sha256_bytes(content)
        if {"assigned_to", "project_name", "summary", "actual_duration_hours", "state"}.issubset(dataframe.columns):
            entries, warnings = normalize_template_timesheet_data(dataframe, source_file, source_hash)
        else:
            entries, warnings = normalize_timesheet_data(dataframe, source_file, source_hash)
        return entries, warnings, source_hash

    def save_entries(
        self,
        source_file: str,
        source_hash: str,
        entries: list[TimesheetEntry],
        replace_existing: bool = False,
    ) -> int:
        logger.info("Import start for %s", source_file)
        if replace_existing:
            import_id = self.repository.replace_dataset_with_import(source_file, source_hash, entries)
        else:
            import_id = self.repository.save_import_with_entries(source_file, source_hash, entries)
        st.cache_data.clear()
        logger.info("Import success for %s with %s rows", source_file, len(entries))
        return import_id

    def reset_dataset(self) -> None:
        self.repository.reset_dataset()
        st.cache_data.clear()

    def load_imported_dataframe(self) -> pd.DataFrame:
        entries = self.repository.load_timesheet_entries()
        return pd.DataFrame([entry.model_dump(mode="json") for entry in entries])


class GraphService:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.import_service = ImportService(db_path)
        self.builder = GraphBuilder()
        self.dataset_service = TimesheetDataService(db_path)

    def load_source_dataframe(self) -> pd.DataFrame:
        return self.dataset_service.load_active_dataset()

    def build_graph(
        self,
        filters: GraphFilterConfig,
        strategy: GraphStrategy = GraphStrategy.SEQUENTIAL,
    ) -> GraphBuildResult:
        source_dataframe = self.load_source_dataframe()
        filtered_dataframe = apply_graph_filters(source_dataframe, filters)
        return self.builder.build(filtered_dataframe, GraphBuildConfig(strategy=strategy))


class TimesheetDataService:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.import_service = ImportService(db_path)
        self.repository = self.import_service.repository

    def load_active_dataset(self) -> pd.DataFrame:
        return load_active_dataset(str(self.db_path), self.get_dataset_version())

    def get_active_dataset(self) -> pd.DataFrame:
        return self.load_active_dataset()

    def get_dataset_version(self) -> str:
        latest_import = self.repository.get_latest_successful_import()
        if latest_import is None:
            return f"{self.db_path.resolve()}::empty"
        return f"{self.db_path.resolve()}::{latest_import.source_hash}::{latest_import.imported_at.isoformat()}"

    def get_dataset_summary(self, dataframe: pd.DataFrame | None = None) -> DatasetSummary:
        dataset = dataframe if dataframe is not None else self.load_active_dataset()
        return get_dataset_summary(dataset)

    def get_data_source_debug(self) -> dict[str, object]:
        dataframe = self.load_active_dataset()
        summary = self.get_dataset_summary(dataframe)
        latest_import = self.repository.get_latest_successful_import()
        return {
            "database_path": str(self.db_path.resolve()),
            "row_count": summary.row_count,
            "employee_count": summary.employee_count,
            "project_count": summary.project_count,
            "task_count": summary.task_count,
            "start_date": summary.start_date.isoformat() if summary.start_date else None,
            "end_date": summary.end_date.isoformat() if summary.end_date else None,
            "latest_import_hash": latest_import.source_hash if latest_import else None,
            "latest_import_timestamp": latest_import.imported_at.isoformat() if latest_import else None,
        }

    def load_import_history(self) -> pd.DataFrame:
        imports = self.repository.load_imports()
        if not imports:
            return pd.DataFrame(
                columns=["source_file", "imported_at", "row_count", "status", "source_hash"]
            )
        return pd.DataFrame([record.model_dump(mode="json") for record in imports])


@st.cache_data(show_spinner=False)
def load_active_dataset(db_path: str, dataset_version: str) -> pd.DataFrame:
    service = ImportService(Path(db_path))
    return service.load_imported_dataframe()


def get_dataset_summary(dataframe: pd.DataFrame) -> DatasetSummary:
    if dataframe.empty:
        return DatasetSummary(
            row_count=0,
            employee_count=0,
            project_count=0,
            task_count=0,
            state_count=0,
            total_hours=0.0,
            start_date=None,
            end_date=None,
        )

    work_dates = pd.to_datetime(dataframe["work_date"])
    task_series = dataframe["task_key"] if "task_key" in dataframe.columns else dataframe.get("task", pd.Series(dtype=str))
    state_series = dataframe["state"] if "state" in dataframe.columns else pd.Series(dtype=str)
    hours_series = dataframe["hours"] if "hours" in dataframe.columns else pd.Series(dtype=float)
    return DatasetSummary(
        row_count=int(len(dataframe)),
        employee_count=int(dataframe["employee"].dropna().nunique()),
        project_count=int(dataframe["project"].dropna().nunique()),
        task_count=int(task_series.dropna().nunique()),
        state_count=int(state_series.dropna().nunique()),
        total_hours=float(pd.to_numeric(hours_series, errors="coerce").fillna(0).sum()),
        start_date=work_dates.min().date(),
        end_date=work_dates.max().date(),
    )
