import pandas as pd

from src.graph.collaboration import (
    apply_collaboration_threshold,
    build_collaboration_clusters,
    build_collaboration_graph,
    build_key_connectors,
    build_low_connectivity,
    build_ranked_collaborators,
    build_strongest_pairs,
)


def _dataset() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"employee": "A", "work_date": "2026-08-01", "project": "P1", "task": "Task X", "task_key": "P1::Task X", "hours": 2},
            {"employee": "B", "work_date": "2026-08-01", "project": "P1", "task": "Task X", "task_key": "P1::Task X", "hours": 1},
            {"employee": "B", "work_date": "2026-08-02", "project": "P1", "task": "Task X", "task_key": "P1::Task X", "hours": 3},
            {"employee": "A", "work_date": "2026-08-03", "project": "P2", "task": "Task Y", "task_key": "P2::Task Y", "hours": 2},
            {"employee": "C", "work_date": "2026-08-08", "project": "P2", "task": "Task Y", "task_key": "P2::Task Y", "hours": 4},
            {"employee": "A", "work_date": "2026-08-10", "project": "P1", "task": "Task W", "task_key": "P1::Task W", "hours": 1},
            {"employee": "B", "work_date": "2026-08-10", "project": "P1", "task": "Task W", "task_key": "P1::Task W", "hours": 2},
            {"employee": "D", "work_date": "2026-08-09", "project": "P3", "task": "Task Z", "task_key": "P3::Task Z", "hours": 5},
        ]
    )


def test_collaboration_graph_links_employees_by_shared_task_across_dates():
    result = build_collaboration_graph(_dataset())

    assert result.graph.has_edge("A", "B")
    assert result.graph.has_edge("A", "C")
    assert not result.graph.has_edge("B", "C")
    assert "D" in result.graph.nodes
    assert result.graph.degree["D"] == 0

    ab = result.edge_dataframe[(result.edge_dataframe["source"] == "A") & (result.edge_dataframe["target"] == "B")].iloc[0]
    assert ab["shared_task_count"] == 2
    assert ab["shared_task_keys"] == ["P1::Task W", "P1::Task X"]

    node_a = result.node_dataframe[result.node_dataframe["employee"] == "A"].iloc[0]
    assert node_a["collaborator_count"] == 2
    assert node_a["collaborative_task_count"] == 3
    assert result.summary.employees == 4
    assert result.summary.collaboration_links == 2
    assert result.summary.collaborative_tasks == 3


def test_threshold_rebuilds_nodes_metrics_and_isolated_visibility():
    result = build_collaboration_graph(_dataset())

    active = apply_collaboration_threshold(result, 2, include_isolated=False)
    assert set(active.graph.nodes) == {"A", "B"}
    assert active.graph.number_of_edges() == 1
    assert active.summary.employees == 2
    assert active.summary.collaboration_links == 1
    assert active.summary.collaborative_tasks == 2

    node_a = active.node_dataframe[active.node_dataframe["employee"] == "A"].iloc[0]
    assert node_a["collaborator_count"] == 1
    assert node_a["collaborative_task_count"] == 2
    assert node_a["project_count"] == 1
    assert node_a["collaborative_hours"] == 3.0

    with_isolated = apply_collaboration_threshold(result, 2, include_isolated=True)
    assert set(with_isolated.graph.nodes) == {"A", "B", "C", "D"}
    assert with_isolated.graph.degree["C"] == 0
    assert with_isolated.graph.degree["D"] == 0
    node_c = with_isolated.node_dataframe[with_isolated.node_dataframe["employee"] == "C"].iloc[0]
    assert node_c["collaborator_count"] == 0
    assert node_c["collaborative_task_count"] == 0


def test_collaboration_insights_follow_thresholded_graph():
    result = build_collaboration_graph(_dataset())
    active = apply_collaboration_threshold(result, 1, include_isolated=False)
    all_nodes = apply_collaboration_threshold(result, 1, include_isolated=True)

    ranked = build_ranked_collaborators(active.node_dataframe)
    assert ranked.iloc[0]["employee"] == "A"

    pairs = build_strongest_pairs(active.edge_dataframe)
    assert pairs.iloc[0]["source"] == "A"
    assert pairs.iloc[0]["target"] == "B"
    assert pairs.iloc[0]["shared_task_count"] == 2

    connectors = build_key_connectors(active.graph)
    assert connectors.iloc[0]["employee"] == "A"

    low = build_low_connectivity(all_nodes.node_dataframe)
    assert "D" in low["employee"].tolist()

    clusters = build_collaboration_clusters(active.graph)
    assert int(clusters["size"].sum()) == 3
    assert len(clusters) == 1
