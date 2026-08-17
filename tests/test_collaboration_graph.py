import pandas as pd

from src.graph.collaboration import build_collaboration_graph


def test_collaboration_graph_links_employees_by_shared_task_across_dates():
    dataframe = pd.DataFrame(
        [
            {"employee": "A", "work_date": "2026-08-01", "project": "P1", "task": "Task X", "task_key": "P1::Task X", "hours": 2},
            {"employee": "B", "work_date": "2026-08-01", "project": "P1", "task": "Task X", "task_key": "P1::Task X", "hours": 1},
            {"employee": "B", "work_date": "2026-08-02", "project": "P1", "task": "Task X", "task_key": "P1::Task X", "hours": 3},
            {"employee": "A", "work_date": "2026-08-03", "project": "P2", "task": "Task Y", "task_key": "P2::Task Y", "hours": 2},
            {"employee": "C", "work_date": "2026-08-08", "project": "P2", "task": "Task Y", "task_key": "P2::Task Y", "hours": 4},
            {"employee": "D", "work_date": "2026-08-09", "project": "P3", "task": "Task Z", "task_key": "P3::Task Z", "hours": 5},
        ]
    )

    result = build_collaboration_graph(dataframe)

    assert result.graph.has_edge("A", "B")
    assert result.graph.has_edge("A", "C")
    assert not result.graph.has_edge("B", "C")
    assert "D" in result.graph.nodes
    assert result.graph.degree["D"] == 0

    ab = result.edge_dataframe[(result.edge_dataframe["source"] == "A") & (result.edge_dataframe["target"] == "B")].iloc[0]
    assert ab["shared_task_count"] == 1
    assert ab["shared_tasks"] == ["Task X"]

    node_a = result.node_dataframe[result.node_dataframe["employee"] == "A"].iloc[0]
    assert node_a["collaborator_count"] == 2
    assert node_a["collaborative_task_count"] == 2
    assert result.summary.employees == 4
    assert result.summary.collaboration_links == 2
    assert result.summary.collaborative_tasks == 2
