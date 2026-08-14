from __future__ import annotations

import pandas as pd

from src.analytics.concurrency import analyze_concurrency
from src.analytics.continuity import analyze_continuity
from src.analytics.context_switch import analyze_context_switching
from src.analytics.fragmentation import analyze_fragmentation
from src.domain.models import GraphStrategy
from src.graph.builder import GraphFilterConfig, apply_graph_filters
from src.services import GraphService


def build_analytics_dataframe() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "entry_id": "1",
                "employee": "Ari",
                "work_date": "2026-08-01",
                "project": "FORCA ERP",
                "task": "Fix Purchase Order",
                "task_key": "forca erp::fix purchase order",
                "hours": 2.0,
            },
            {
                "entry_id": "2",
                "employee": "Bima",
                "work_date": "2026-08-01",
                "project": "FORCA ERP",
                "task": "Fix Purchase Order",
                "task_key": "forca erp::fix purchase order",
                "hours": 3.0,
            },
            {
                "entry_id": "3",
                "employee": "Ari",
                "work_date": "2026-08-03",
                "project": "FORCA ERP",
                "task": "Fix Purchase Order",
                "task_key": "forca erp::fix purchase order",
                "hours": 2.0,
            },
            {
                "entry_id": "4",
                "employee": "Ari",
                "work_date": "2026-08-07",
                "project": "FORCA ERP",
                "task": "Fix Purchase Order",
                "task_key": "forca erp::fix purchase order",
                "hours": 1.0,
            },
            {
                "entry_id": "5",
                "employee": "Ari",
                "work_date": "2026-08-10",
                "project": "Neural Ops",
                "task": "Task Alpha",
                "task_key": "neural ops::task alpha",
                "hours": 1.0,
            },
            {
                "entry_id": "6",
                "employee": "Ari",
                "work_date": "2026-08-10",
                "project": "Neural Ops",
                "task": "Task Beta",
                "task_key": "neural ops::task beta",
                "hours": 1.5,
            },
            {
                "entry_id": "7",
                "employee": "Ari",
                "work_date": "2026-08-10",
                "project": "FORCA ERP",
                "task": "Task Gamma",
                "task_key": "forca erp::task gamma",
                "hours": 2.0,
            },
            {
                "entry_id": "8",
                "employee": "Citra",
                "work_date": "2026-08-01",
                "project": "Neural Ops",
                "task": "Consecutive Task",
                "task_key": "neural ops::consecutive task",
                "hours": 1.0,
            },
            {
                "entry_id": "9",
                "employee": "Citra",
                "work_date": "2026-08-02",
                "project": "Neural Ops",
                "task": "Consecutive Task",
                "task_key": "neural ops::consecutive task",
                "hours": 1.0,
            },
            {
                "entry_id": "10",
                "employee": "Citra",
                "work_date": "2026-08-03",
                "project": "Neural Ops",
                "task": "Consecutive Task",
                "task_key": "neural ops::consecutive task",
                "hours": 1.0,
            },
            {
                "entry_id": "11",
                "employee": "Dewi",
                "work_date": "2026-08-05",
                "project": "Neural Ops",
                "task": "Single Day Task",
                "task_key": "neural ops::single day task",
                "hours": 4.0,
            },
        ]
    )


def test_fragmentation_non_consecutive_dates() -> None:
    result = analyze_fragmentation(build_analytics_dataframe())
    row = result[result["task_key"] == "forca erp::fix purchase order"].iloc[0]
    assert row["active_days"] == 3
    assert row["calendar_span_days"] == 7
    assert row["continuation_count"] == 2
    assert row["interruption_count"] == 2
    assert row["total_interruption_days"] == 4
    assert row["max_date_gap_days"] == 4
    assert row["fragmentation_score"] == 6


def test_fragmentation_consecutive_task() -> None:
    result = analyze_fragmentation(build_analytics_dataframe())
    row = result[result["task_key"] == "neural ops::consecutive task"].iloc[0]
    assert row["continuation_count"] == 2
    assert row["interruption_count"] == 0
    assert row["total_interruption_days"] == 0
    assert row["fragmentation_score"] == 2


def test_fragmentation_single_day_task() -> None:
    result = analyze_fragmentation(build_analytics_dataframe())
    row = result[result["task_key"] == "neural ops::single day task"].iloc[0]
    assert row["active_days"] == 1
    assert row["calendar_span_days"] == 1
    assert row["fragmentation_score"] == 0
    assert row["continuous_work_ratio"] == 1.0


def test_context_switching_counts_unique_tasks() -> None:
    daily, summary = analyze_context_switching(build_analytics_dataframe())
    row = daily[(daily["employee"] == "Ari") & (daily["work_date"] == pd.Timestamp("2026-08-10"))].iloc[0]
    assert row["unique_tasks"] == 3
    assert row["context_switches"] == 2
    summary_row = summary[summary["employee"] == "Ari"].iloc[0]
    assert summary_row["max_context_switches_single_day"] == 2


def test_continuity_ratio_is_calculated() -> None:
    result = analyze_continuity(build_analytics_dataframe())
    row = result[result["task_key"] == "forca erp::fix purchase order"].iloc[0]
    assert round(float(row["continuous_work_ratio"]), 4) == 0.4286


def test_duplicate_same_day_rows_do_not_inflate_active_days() -> None:
    result = analyze_fragmentation(build_analytics_dataframe())
    row = result[result["task_key"] == "forca erp::fix purchase order"].iloc[0]
    assert row["active_days"] == 3
    assert row["total_hours"] == 8.0


def test_filters_change_analytics_results() -> None:
    filtered = apply_graph_filters(
        build_analytics_dataframe(),
        GraphFilterConfig(
            employee_names=("Citra",),
            projects=("Neural Ops",),
            task_keys=("neural ops::consecutive task",),
            start_date="2026-08-01",
            end_date="2026-08-03",
        ),
    )
    result = analyze_fragmentation(filtered)
    assert len(result) == 1
    assert result.iloc[0]["task_key"] == "neural ops::consecutive task"


def test_concurrency_metrics_are_generated() -> None:
    result = analyze_concurrency(build_analytics_dataframe())
    overall = result["date_overall"]
    row = overall[overall["work_date"] == pd.Timestamp("2026-08-10")].iloc[0]
    assert row["active_tasks"] == 3
    assert row["active_projects"] == 2
    assert row["active_employees"] == 1
