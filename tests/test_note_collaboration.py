import pandas as pd

from src.graph.collaboration_mentions import extract_collaboration_mentions
from src.graph.note_collaboration import apply_note_evidence_threshold, build_note_collaboration_graph


def _frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "entry_id": "1",
                "employee": "Alice Example",
                "note": "Koordinasi dengan Bob untuk deployment.",
                "work_date": "2026-08-01",
                "task_key": "P1::Deploy",
                "task": "Deploy",
                "project": "P1",
                "hours": 2.0,
            },
            {
                "entry_id": "2",
                "employee": "Bob Builder",
                "note": "Review bersama Alice sebelum release.",
                "work_date": "2026-08-02",
                "task_key": "P1::Review",
                "task": "Review",
                "project": "P1",
                "hours": 3.0,
            },
            {
                "entry_id": "3",
                "employee": "Carol Tester",
                "note": "Testing mandiri.",
                "work_date": "2026-08-03",
                "task_key": "P1::Test",
                "task": "Test",
                "project": "P1",
                "hours": 4.0,
            },
            {
                "entry_id": "4",
                "employee": "Alice Example",
                "note": "Masih koordinasi dengan Bob terkait hotfix.",
                "work_date": "2026-08-04",
                "task_key": "P1::Hotfix",
                "task": "Hotfix",
                "project": "P1",
                "hours": 1.0,
            },
        ]
    )


def test_note_mentions_create_collaboration_edges_without_shared_task_requirement() -> None:
    dataframe = _frame()
    mentions = extract_collaboration_mentions(
        dataframe,
        employee_roster=["Alice Example", "Bob Builder", "Carol Tester"],
    )

    result = build_note_collaboration_graph(dataframe, mentions, include_isolated=True)

    assert result.graph.has_edge("Alice Example", "Bob Builder")
    assert not result.graph.has_edge("Alice Example", "Carol Tester")
    assert result.graph.degree["Carol Tester"] == 0

    edge = result.edge_dataframe.iloc[0]
    assert edge["shared_task_count"] == 3
    assert edge["a_to_b_count"] == 2
    assert edge["b_to_a_count"] == 1
    assert set(edge["shared_tasks"]) == {"Deploy", "Review", "Hotfix"}
    assert edge["related_hours"] == 6.0

    alice = result.node_dataframe[result.node_dataframe["employee"] == "Alice Example"].iloc[0]
    assert alice["collaborator_count"] == 1
    assert alice["collaborative_task_count"] == 3
    assert alice["top_collaborators"] == ["Bob Builder (3 evidence)"]

    assert result.summary.collaboration_links == 1
    assert result.summary.collaborative_tasks == 3


def test_note_evidence_threshold_rebuilds_visibility_and_metrics() -> None:
    dataframe = _frame()
    mentions = extract_collaboration_mentions(
        dataframe,
        employee_roster=["Alice Example", "Bob Builder", "Carol Tester"],
    )
    result = build_note_collaboration_graph(dataframe, mentions, include_isolated=True)

    active = apply_note_evidence_threshold(result, 3, include_isolated=False)
    hidden = apply_note_evidence_threshold(result, 4, include_isolated=False)
    all_nodes = apply_note_evidence_threshold(result, 4, include_isolated=True)

    assert active.summary.collaboration_links == 1
    assert active.summary.employees == 2
    assert hidden.summary.collaboration_links == 0
    assert hidden.summary.employees == 0
    assert all_nodes.summary.employees == 3
    assert all_nodes.node_dataframe["collaborator_count"].sum() == 0
