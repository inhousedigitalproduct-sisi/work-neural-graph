import pandas as pd

from src.graph.collaboration_mentions import (
    build_acknowledgement_insights,
    build_mention_diagnostics,
    build_visible_directional_signals,
    extract_collaboration_mentions,
)


def _frame(rows: list[dict[str, object]]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def test_extracts_one_way_mentions_once_per_timesheet_entry() -> None:
    dataframe = _frame(
        [
            {
                "entry_id": "1",
                "employee": "Alice Example",
                "note": "Review bersama Bob Builder. Bob Builder sudah memberi feedback.",
                "work_date": "2026-08-17",
                "task_key": "T-1",
                "project": "Alpha",
            },
            {
                "entry_id": "2",
                "employee": "Bob Builder",
                "note": "Implementasi modul tanpa menyebut rekan.",
                "work_date": "2026-08-17",
                "task_key": "T-1",
                "project": "Alpha",
            },
        ]
    )

    result = extract_collaboration_mentions(dataframe)

    assert len(result.evidence_dataframe) == 1
    evidence = result.evidence_dataframe.iloc[0]
    assert evidence["source_employee"] == "Alice Example"
    assert evidence["target_employee"] == "Bob Builder"
    assert evidence["entry_id"] == "1"
    assert result.directional_dataframe.iloc[0]["acknowledgement_entry_count"] == 1


def test_unique_automatic_single_name_is_allowed_but_ambiguous_name_is_rejected() -> None:
    unique_dataframe = _frame(
        [
            {
                "entry_id": "1",
                "employee": "Alice Example",
                "note": "Diskusi dengan Bob terkait deployment.",
                "task_key": "T-1",
                "project": "Alpha",
            }
        ]
    )
    unique_roster = ["Alice Example", "Bob Builder"]

    unique = extract_collaboration_mentions(unique_dataframe, employee_roster=unique_roster)

    assert unique.evidence_dataframe.iloc[0]["target_employee"] == "Bob Builder"
    assert unique.evidence_dataframe.iloc[0]["matched_alias"] == "bob"
    assert unique.evidence_dataframe.iloc[0]["confidence"] == 0.92

    ambiguous_roster = ["Alice Example", "Bob Builder", "Bob Brown"]
    ambiguous = extract_collaboration_mentions(unique_dataframe, employee_roster=ambiguous_roster)

    assert ambiguous.evidence_dataframe.empty
    assert ambiguous.directional_dataframe.empty


def test_manual_alias_still_supports_nickname_not_present_in_canonical_name() -> None:
    dataframe = _frame(
        [
            {
                "entry_id": "1",
                "employee": "Alice Example",
                "note": "Koordinasi dengan Bobby terkait deployment.",
                "task_key": "T-1",
                "project": "Alpha",
            }
        ]
    )

    result = extract_collaboration_mentions(
        dataframe,
        employee_roster=["Alice Example", "Bob Builder"],
        aliases={"Bob Builder": ["Bobby"]},
    )

    assert result.evidence_dataframe.iloc[0]["target_employee"] == "Bob Builder"
    assert result.evidence_dataframe.iloc[0]["confidence"] == 0.98


def test_mention_diagnostics_explain_when_visible_signals_are_missing() -> None:
    dataframe = _frame(
        [
            {
                "entry_id": "1",
                "employee": "Alice Example",
                "note": "Diskusi dengan Bob terkait deployment.",
                "task_key": "T-1",
                "project": "Alpha",
            },
            {
                "entry_id": "2",
                "employee": "Bob Builder",
                "note": "Implementasi mandiri.",
                "task_key": "T-1",
                "project": "Alpha",
            },
            {
                "entry_id": "3",
                "employee": "Alice Example",
                "note": None,
                "task_key": "T-2",
                "project": "Alpha",
            },
        ]
    )
    result = extract_collaboration_mentions(dataframe, employee_roster=["Alice Example", "Bob Builder"])
    diagnostics = build_mention_diagnostics(dataframe, result, visible_signals=[])

    assert diagnostics == {
        "notes_scanned": 2,
        "notes_with_accepted_evidence": 1,
        "notes_without_accepted_evidence": 1,
        "accepted_evidence": 1,
        "directional_pairs": 1,
        "visible_signals": 0,
    }


def test_builds_mutual_one_sided_silent_and_mention_only_insights() -> None:
    shared_edges = _frame(
        [
            {"source": "Alice Example", "target": "Bob Builder", "shared_task_count": 4},
            {"source": "Alice Example", "target": "Carol Tester", "shared_task_count": 2},
            {"source": "Bob Builder", "target": "Carol Tester", "shared_task_count": 1},
        ]
    )
    directional = _frame(
        [
            {"source_employee": "Alice Example", "target_employee": "Bob Builder", "acknowledgement_entry_count": 3},
            {"source_employee": "Bob Builder", "target_employee": "Alice Example", "acknowledgement_entry_count": 2},
            {"source_employee": "Alice Example", "target_employee": "Carol Tester", "acknowledgement_entry_count": 2},
            {"source_employee": "Carol Tester", "target_employee": "Dina Analyst", "acknowledgement_entry_count": 1},
        ]
    )

    insights = build_acknowledgement_insights(shared_edges, directional)
    types = {
        (row.employee_a, row.employee_b): row.evidence_type
        for row in insights.itertuples(index=False)
    }

    assert types[("Alice Example", "Bob Builder")] == "SHARED_MUTUAL"
    assert types[("Alice Example", "Carol Tester")] == "SHARED_ONE_SIDED"
    assert types[("Bob Builder", "Carol Tester")] == "SHARED_SILENT"
    assert types[("Carol Tester", "Dina Analyst")] == "MENTION_ONLY"

    mutual = insights[(insights["employee_a"] == "Alice Example") & (insights["employee_b"] == "Bob Builder")].iloc[0]
    assert mutual["acknowledgement_reciprocity"] == 0.8


def test_visible_directional_signals_keep_direction_and_exclude_mention_only_pairs() -> None:
    directional = _frame(
        [
            {"source_employee": "Alice Example", "target_employee": "Bob Builder", "acknowledgement_entry_count": 3},
            {"source_employee": "Bob Builder", "target_employee": "Alice Example", "acknowledgement_entry_count": 2},
            {"source_employee": "Carol Tester", "target_employee": "Dina Analyst", "acknowledgement_entry_count": 1},
        ]
    )
    visible_edges = _frame(
        [{"source": "Alice Example", "target": "Bob Builder", "shared_task_count": 4}]
    )

    signals = build_visible_directional_signals(directional, visible_edges)

    assert signals == [
        {"source": "Alice Example", "target": "Bob Builder", "count": 3},
        {"source": "Bob Builder", "target": "Alice Example", "count": 2},
    ]
