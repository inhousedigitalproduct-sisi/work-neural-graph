from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pandas as pd

from src.analytics.service import AnalyticsService
from src.database.repository import TimesheetRepository
from src.domain.models import TimesheetEntry
from src.graph.builder import GraphFilterConfig
from src.services import GraphService, ImportService, TimesheetDataService, get_dataset_summary


def build_entry(
    entry_id: str,
    employee: str,
    project: str,
    task: str,
    work_date: date,
    source_hash: str,
) -> TimesheetEntry:
    return TimesheetEntry(
        entry_id=entry_id,
        assigned_to=employee,
        project_name=project,
        summary=task,
        note=None,
        completed_date=work_date,
        actual_start=datetime.combine(work_date, datetime.min.time()),
        actual_finish=None,
        actual_duration_hours=1.0,
        state="Done",
        employee=employee,
        work_date=work_date,
        project=project,
        task=task,
        task_key=f"{project.lower()}::{task.lower()}",
        hours=1.0,
        source_file="test.xlsx",
        source_hash=source_hash,
        source_sheet="Sheet1",
        source_row=2,
    )


def test_repository_source_of_truth_returns_imported_employees_only(temp_db_path) -> None:
    repository = TimesheetRepository(temp_db_path)
    repository.save_import_with_entries(
        "test.xlsx",
        "hash-a",
        [
            build_entry("1", "Budi Darmanto", "Prod Dev", "Task A", date(2026, 8, 12), "hash-a"),
            build_entry("2", "Dewi Example", "Prod Dev", "Task B", date(2026, 8, 13), "hash-a"),
        ],
    )
    dataset = TimesheetDataService(temp_db_path).load_active_dataset()
    employees = set(dataset["employee"].tolist())
    assert employees == {"Budi Darmanto", "Dewi Example"}
    assert employees.isdisjoint({"Ari", "Bima", "Citra"})


def test_timesheet_data_service_exposes_load_active_dataset(temp_db_path) -> None:
    data_service = TimesheetDataService(temp_db_path)
    assert hasattr(data_service, "load_active_dataset")
    dataset = data_service.load_active_dataset()
    assert isinstance(dataset, pd.DataFrame)


def test_cache_freshness_uses_latest_import_version(temp_db_path) -> None:
    repository = TimesheetRepository(temp_db_path)
    data_service = TimesheetDataService(temp_db_path)

    repository.save_import_with_entries(
        "a.xlsx",
        "hash-a",
        [build_entry("1", "Budi Darmanto", "Prod Dev", "Task A", date(2026, 8, 12), "hash-a")],
    )
    version_a = data_service.get_dataset_version()
    dataset_a = data_service.load_active_dataset()
    assert set(dataset_a["employee"]) == {"Budi Darmanto"}

    repository.save_import_with_entries(
        "b.xlsx",
        "hash-b",
        [build_entry("2", "Dewi Example", "Prod Dev", "Task B", date(2026, 8, 13), "hash-b")],
    )
    version_b = data_service.get_dataset_version()
    dataset_b = data_service.load_active_dataset()
    assert version_b != version_a
    assert set(dataset_b["employee"]) == {"Budi Darmanto", "Dewi Example"}


def test_replace_mode_refreshes_dataset_and_filter_source(temp_db_path) -> None:
    import_service = ImportService(temp_db_path)
    data_service = TimesheetDataService(temp_db_path)

    import_service.save_entries(
        "a.xlsx",
        "hash-a",
        [build_entry("1", "Budi Darmanto", "Prod Dev", "Task A", date(2026, 8, 12), "hash-a")],
        replace_existing=True,
    )
    dataset_a = data_service.load_active_dataset()
    assert set(dataset_a["employee"]) == {"Budi Darmanto"}

    import_service.save_entries(
        "b.xlsx",
        "hash-b",
        [build_entry("2", "Dewi Example", "Project Beta", "Task B", date(2026, 8, 13), "hash-b")],
        replace_existing=True,
    )
    dataset_b = data_service.load_active_dataset()
    assert set(dataset_b["employee"]) == {"Dewi Example"}
    assert set(dataset_b["project"]) == {"Project Beta"}


def test_dashboard_and_neural_graph_services_share_same_db_path(temp_db_path) -> None:
    import_service = ImportService(temp_db_path)
    graph_service = GraphService(temp_db_path)
    analytics_service = AnalyticsService(temp_db_path)
    data_service = TimesheetDataService(temp_db_path)

    assert import_service.db_path.resolve() == temp_db_path.resolve()
    assert graph_service.db_path.resolve() == temp_db_path.resolve()
    assert analytics_service.graph_service.db_path.resolve() == temp_db_path.resolve()
    assert data_service.db_path.resolve() == temp_db_path.resolve()


def test_empty_database_returns_empty_dataset_and_no_sample_fallback(temp_db_path) -> None:
    dataset = TimesheetDataService(temp_db_path).load_active_dataset()
    summary = get_dataset_summary(dataset)
    assert dataset.empty
    assert summary.row_count == 0
    assert summary.employee_count == 0


def test_reset_dataset_clears_entries_and_import_history(temp_db_path) -> None:
    import_service = ImportService(temp_db_path)
    repository = TimesheetRepository(temp_db_path)

    import_service.save_entries(
        "test.xlsx",
        "hash-a",
        [build_entry("1", "Budi Darmanto", "Prod Dev", "Task A", date(2026, 8, 12), "hash-a")],
        replace_existing=True,
    )
    assert not TimesheetDataService(temp_db_path).load_active_dataset().empty
    assert len(repository.load_imports()) == 1

    import_service.reset_dataset()

    assert TimesheetDataService(temp_db_path).load_active_dataset().empty
    assert repository.load_imports() == []


def test_graph_service_build_graph_works_without_attribute_error(temp_db_path) -> None:
    repository = TimesheetRepository(temp_db_path)
    repository.save_import_with_entries(
        "test.xlsx",
        "hash-a",
        [build_entry("1", "Budi Darmanto", "Prod Dev", "Task A", date(2026, 8, 12), "hash-a")],
    )
    result = GraphService(temp_db_path).build_graph(filters=GraphFilterConfig())
    assert result.summary.nodes == 1
    assert result.filtered_dataframe.iloc[0]["employee"] == "Budi Darmanto"


def test_dashboard_snapshot_builds_successfully(temp_db_path) -> None:
    repository = TimesheetRepository(temp_db_path)
    repository.save_import_with_entries(
        "test.xlsx",
        "hash-a",
        [
            build_entry("1", "Budi Darmanto", "Prod Dev", "Task A", date(2026, 8, 12), "hash-a"),
            build_entry("2", "Dewi Example", "Prod Dev", "Task B", date(2026, 8, 13), "hash-a"),
        ],
    )
    snapshot = AnalyticsService(temp_db_path).build_snapshot(filters=GraphFilterConfig())
    assert not snapshot.filtered_dataframe.empty
    assert snapshot.kpi.total_hours == 2.0
    assert snapshot.kpi.unique_employees == 2
    assert snapshot.kpi.unique_projects == 1


def test_validation_failure_does_not_clear_existing_dataset(temp_db_path) -> None:
    import_service = ImportService(temp_db_path)
    import_service.save_entries(
        "existing.xlsx",
        "hash-a",
        [build_entry("1", "Budi Darmanto", "Prod Dev", "Task A", date(2026, 8, 12), "hash-a")],
        replace_existing=True,
    )

    invalid_dataframe = pd.DataFrame(
        [
            {
                "assigned_to": "",
                "project_name": "Project Beta",
                "summary": "Task B",
                "actual_duration_hours": 3,
                "state": "Done",
            }
        ]
    )

    try:
        import_service.normalize_entries(
            invalid_dataframe,
            source_file="invalid.xlsx",
            content=b"invalid",
        )
    except ValueError:
        pass
    else:
        raise AssertionError("Expected invalid normalization to fail")

    dataset = TimesheetDataService(temp_db_path).load_active_dataset()
    assert set(dataset["employee"]) == {"Budi Darmanto"}


def test_load_import_history_returns_repository_records(temp_db_path) -> None:
    repository = TimesheetRepository(temp_db_path)
    repository.save_import_with_entries(
        "history.xlsx",
        "hash-history",
        [build_entry("1", "Budi Darmanto", "Prod Dev", "Task A", date(2026, 8, 12), "hash-history")],
    )

    history = TimesheetDataService(temp_db_path).load_import_history()
    assert list(history["source_file"]) == ["history.xlsx"]
    assert list(history["status"]) == ["SUCCESS"]
    assert list(history["row_count"]) == [1]


def test_imported_filters_come_from_dataset_columns() -> None:
    dataframe = pd.DataFrame(
        [
            {
                "employee": "Budi Darmanto",
                "project": "Project Alpha",
                "task": "Summary A",
                "task_key": "project alpha::summary a",
                "state": "Done",
                "note": "alpha note",
                "work_date": "2026-08-12",
            },
            {
                "employee": "Dewi Example",
                "project": "Project Beta",
                "task": "Summary B",
                "task_key": "project beta::summary b",
                "state": "In Progress",
                "note": "beta note",
                "work_date": "2026-08-13",
            },
        ]
    )
    summary = get_dataset_summary(dataframe)
    assert summary.employee_count == 2
    assert summary.project_count == 2
    assert summary.task_count == 2


def test_app_navigation_uses_load_data_page_and_no_app_page_content() -> None:
    app_source = Path("app.py").read_text(encoding="utf-8")
    assert 'st.Page("pages/1_Load_Data.py", title="Load Data", default=True)' in app_source
    assert "st.navigation(" in app_source
    assert "st.title(" not in app_source


def test_load_data_page_has_no_runtime_sample_dataset_reference() -> None:
    load_data_source = Path("pages/1_Load_Data.py").read_text(encoding="utf-8")
    assert "sample_timesheet.csv" not in load_data_source
