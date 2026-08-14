from __future__ import annotations

import pandas as pd

from src.domain.models import GraphStrategy
from src.graph.builder import GraphBuildConfig, GraphBuilder, GraphFilterConfig, apply_graph_filters


def build_graph_dataframe() -> pd.DataFrame:
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
                "employee": "Citra",
                "work_date": "2026-08-01",
                "project": "Neural Ops",
                "task": "Shared QA Review",
                "task_key": "neural ops::shared qa review",
                "hours": 1.0,
            },
            {
                "entry_id": "6",
                "employee": "Citra",
                "work_date": "2026-08-03",
                "project": "Neural Ops",
                "task": "Shared QA Review",
                "task_key": "neural ops::shared qa review",
                "hours": 1.0,
            },
            {
                "entry_id": "7",
                "employee": "Dewi",
                "work_date": "2026-08-05",
                "project": "Neural Ops",
                "task": "One Day Task",
                "task_key": "neural ops::one day task",
                "hours": 4.0,
            },
        ]
    )


def test_sequential_relationships_only_connect_adjacent_dates() -> None:
    builder = GraphBuilder()
    result = builder.build(build_graph_dataframe(), GraphBuildConfig(strategy=GraphStrategy.SEQUENTIAL))

    actual_pairs = {
        (row["source_date"].date().isoformat(), row["target_date"].date().isoformat())
        for row in result.relationship_dataframe.to_dict(orient="records")
        if row["task_key"] == "forca erp::fix purchase order"
    }
    assert actual_pairs == {("2026-08-01", "2026-08-03"), ("2026-08-03", "2026-08-07")}


def test_all_to_all_relationships_include_non_adjacent_dates() -> None:
    builder = GraphBuilder()
    result = builder.build(build_graph_dataframe(), GraphBuildConfig(strategy=GraphStrategy.ALL_TO_ALL))

    actual_pairs = {
        (row["source_date"].date().isoformat(), row["target_date"].date().isoformat())
        for row in result.relationship_dataframe.to_dict(orient="records")
        if row["task_key"] == "forca erp::fix purchase order"
    }
    assert actual_pairs == {
        ("2026-08-01", "2026-08-03"),
        ("2026-08-01", "2026-08-07"),
        ("2026-08-03", "2026-08-07"),
    }


def test_duplicate_same_date_entries_do_not_create_self_links() -> None:
    builder = GraphBuilder()
    result = builder.build(build_graph_dataframe(), GraphBuildConfig(strategy=GraphStrategy.SEQUENTIAL))

    source_targets = result.relationship_dataframe[["source_date", "target_date"]].drop_duplicates()
    assert not any(source_targets["source_date"] == source_targets["target_date"])


def test_edge_aggregation_combines_multiple_tasks_for_same_date_pair() -> None:
    builder = GraphBuilder()
    result = builder.build(build_graph_dataframe(), GraphBuildConfig(strategy=GraphStrategy.SEQUENTIAL))

    edge = result.edge_dataframe.iloc[0]
    assert edge["source"].date().isoformat() == "2026-08-01"
    assert edge["target"].date().isoformat() == "2026-08-03"
    assert edge["task_count"] == 2
    assert sorted(edge["shared_tasks"]) == ["Fix Purchase Order", "Shared QA Review"]


def test_node_metrics_are_calculated_correctly() -> None:
    builder = GraphBuilder()
    result = builder.build(build_graph_dataframe(), GraphBuildConfig(strategy=GraphStrategy.SEQUENTIAL))

    node = result.node_dataframe[result.node_dataframe["date"] == pd.Timestamp("2026-08-01")].iloc[0]
    assert node["total_hours"] == 6.0
    assert node["unique_tasks"] == 2
    assert node["unique_employees"] == 3
    assert node["unique_projects"] == 2
    assert node["degree"] == 1


def test_filters_apply_before_graph_generation() -> None:
    dataframe = build_graph_dataframe()
    filtered = apply_graph_filters(
        dataframe,
        GraphFilterConfig(
            employee_names=("Ari",),
            projects=("FORCA ERP",),
            task_keys=("forca erp::fix purchase order",),
            start_date="2026-08-01",
            end_date="2026-08-03",
        ),
    )
    assert len(filtered) == 2
    assert set(filtered["employee"]) == {"Ari"}
    assert set(filtered["project"]) == {"FORCA ERP"}


def test_empty_graph_does_not_raise_and_has_zero_summary() -> None:
    builder = GraphBuilder()
    result = builder.build(pd.DataFrame(), GraphBuildConfig(strategy=GraphStrategy.SEQUENTIAL))

    assert result.summary.nodes == 0
    assert result.summary.edges == 0
    assert result.graph.number_of_nodes() == 0
    assert result.graph.number_of_edges() == 0


def test_sequential_relationships_keep_cross_year_dates_unambiguous() -> None:
    dataframe = pd.DataFrame(
        [
            {"entry_id": "1", "employee": "Ari", "work_date": "2025-12-31", "project": "P", "task": "Cross Year Task", "task_key": "p::cross year task", "hours": 1.0},
            {"entry_id": "2", "employee": "Ari", "work_date": "2026-01-01", "project": "P", "task": "Cross Year Task", "task_key": "p::cross year task", "hours": 1.0},
            {"entry_id": "3", "employee": "Ari", "work_date": "2026-01-02", "project": "P", "task": "Cross Year Task", "task_key": "p::cross year task", "hours": 1.0},
            {"entry_id": "4", "employee": "Ari", "work_date": "2026-01-07", "project": "P", "task": "Cross Year Task", "task_key": "p::cross year task", "hours": 1.0},
        ]
    )
    result = GraphBuilder().build(dataframe, GraphBuildConfig(strategy=GraphStrategy.SEQUENTIAL))
    pairs = [
        (row["source_date"].date().isoformat(), row["target_date"].date().isoformat())
        for row in result.relationship_dataframe.to_dict(orient="records")
    ]
    assert pairs == [
        ("2025-12-31", "2026-01-01"),
        ("2026-01-01", "2026-01-02"),
        ("2026-01-02", "2026-01-07"),
    ]
