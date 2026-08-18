from __future__ import annotations

from collections.abc import Iterable

import networkx as nx
import pandas as pd

from src.graph.collaboration import CollaborationGraphResult, CollaborationSummary
from src.graph.collaboration_mentions import CollaborationMentionResult


EDGE_COLUMNS = [
    "source",
    "target",
    "shared_task_count",
    "shared_task_keys",
    "shared_tasks",
    "projects",
    "related_hours",
    "a_to_b_count",
    "b_to_a_count",
    "evidence_entry_ids",
]
NODE_COLUMNS = [
    "employee",
    "collaborator_count",
    "collaborative_task_count",
    "project_count",
    "collaborative_hours",
    "collaborators",
    "top_collaborators",
    "top_tasks",
]


def _prepared_dataframe(dataframe: pd.DataFrame) -> pd.DataFrame:
    prepared = dataframe.copy()
    if prepared.empty:
        return prepared
    prepared["employee"] = prepared.get("employee", "").fillna("").astype(str).str.strip()
    prepared = prepared[prepared["employee"].ne("")].copy()
    prepared["hours"] = pd.to_numeric(prepared.get("hours", 0.0), errors="coerce").fillna(0.0)
    if "entry_id" not in prepared.columns:
        prepared["entry_id"] = prepared.index.astype(str)
    else:
        fallback = prepared.index.astype(str)
        prepared["entry_id"] = prepared["entry_id"].where(prepared["entry_id"].notna(), fallback).astype(str)
    for column in ["task_key", "task", "project"]:
        if column not in prepared.columns:
            prepared[column] = ""
    return prepared


def _entry_context(prepared: pd.DataFrame) -> dict[str, dict[str, object]]:
    context: dict[str, dict[str, object]] = {}
    for row in prepared.to_dict(orient="records"):
        entry_id = str(row.get("entry_id", "")).strip()
        if not entry_id or entry_id in context:
            continue
        context[entry_id] = {
            "hours": float(row.get("hours", 0.0) or 0.0),
            "task_key": str(row.get("task_key", "") or "").strip(),
            "task": str(row.get("task", "") or "").strip(),
            "project": str(row.get("project", "") or "").strip(),
        }
    return context


def _flatten(values: Iterable[object]) -> set[str]:
    flattened: set[str] = set()
    for value in values:
        if isinstance(value, (list, tuple, set)):
            flattened.update(str(item) for item in value if str(item).strip())
        elif value is not None and str(value).strip():
            flattened.add(str(value))
    return flattened


def _build_result_from_edges(
    prepared: pd.DataFrame,
    edge_dataframe: pd.DataFrame,
    *,
    include_isolated: bool,
) -> CollaborationGraphResult:
    graph = nx.Graph()
    all_employees = sorted(prepared["employee"].dropna().astype(str).unique().tolist()) if not prepared.empty else []
    if include_isolated:
        graph.add_nodes_from(all_employees)

    for edge in edge_dataframe.to_dict(orient="records"):
        source = str(edge["source"])
        target = str(edge["target"])
        graph.add_edge(
            source,
            target,
            shared_task_count=int(edge.get("shared_task_count", 0) or 0),
            evidence_count=int(edge.get("shared_task_count", 0) or 0),
            a_to_b_count=int(edge.get("a_to_b_count", 0) or 0),
            b_to_a_count=int(edge.get("b_to_a_count", 0) or 0),
            shared_tasks=list(edge.get("shared_tasks", []) or []),
            projects=list(edge.get("projects", []) or []),
            related_hours=float(edge.get("related_hours", 0.0) or 0.0),
            evidence_entry_ids=list(edge.get("evidence_entry_ids", []) or []),
        )

    entry_context = _entry_context(prepared)
    node_rows: list[dict[str, object]] = []
    for employee in sorted(graph.nodes):
        collaborators = sorted(graph.neighbors(employee))
        collaborator_strength: list[tuple[str, int]] = []
        evidence_entry_ids: set[str] = set()
        projects: set[str] = set()
        tasks: set[str] = set()
        evidence_count = 0
        for collaborator in collaborators:
            edge = graph.get_edge_data(employee, collaborator) or {}
            count = int(edge.get("evidence_count", edge.get("shared_task_count", 0)) or 0)
            evidence_count += count
            collaborator_strength.append((collaborator, count))
            evidence_entry_ids.update(str(value) for value in edge.get("evidence_entry_ids", []) if value)
            projects.update(str(value) for value in edge.get("projects", []) if value)
            tasks.update(str(value) for value in edge.get("shared_tasks", []) if value)

        collaborator_strength.sort(key=lambda item: (-item[1], item[0]))
        top_collaborators = [f"{name} ({count} evidence)" for name, count in collaborator_strength[:5]]
        related_hours = round(
            sum(float(entry_context.get(entry_id, {}).get("hours", 0.0) or 0.0) for entry_id in evidence_entry_ids),
            2,
        )
        node_rows.append(
            {
                "employee": employee,
                "collaborator_count": int(graph.degree[employee]),
                # Compatibility field used by the existing Sigma renderer; semantic is Note evidence count.
                "collaborative_task_count": int(evidence_count),
                "project_count": int(len(projects)),
                "collaborative_hours": related_hours,
                "collaborators": collaborators,
                "top_collaborators": top_collaborators,
                "top_tasks": sorted(tasks)[:5],
            }
        )

    node_dataframe = pd.DataFrame(node_rows, columns=NODE_COLUMNS)
    all_entry_ids = _flatten(edge_dataframe.get("evidence_entry_ids", pd.Series(dtype=object)).tolist()) if not edge_dataframe.empty else set()
    all_projects = _flatten(edge_dataframe.get("projects", pd.Series(dtype=object)).tolist()) if not edge_dataframe.empty else set()
    total_evidence = int(pd.to_numeric(edge_dataframe.get("shared_task_count", pd.Series(dtype=float)), errors="coerce").fillna(0).sum()) if not edge_dataframe.empty else 0
    total_hours = round(
        sum(float(entry_context.get(entry_id, {}).get("hours", 0.0) or 0.0) for entry_id in all_entry_ids),
        2,
    )
    degrees = [degree for _, degree in graph.degree()]
    summary = CollaborationSummary(
        employees=int(graph.number_of_nodes()),
        collaboration_links=int(graph.number_of_edges()),
        # Compatibility field; semantic is accepted Note collaboration evidence.
        collaborative_tasks=total_evidence,
        projects=int(len(all_projects)),
        collaborative_hours=total_hours,
        average_collaborators=round(float(sum(degrees) / len(degrees)), 2) if degrees else 0.0,
    )
    return CollaborationGraphResult(
        filtered_dataframe=prepared,
        node_dataframe=node_dataframe,
        edge_dataframe=edge_dataframe.reset_index(drop=True),
        graph=graph,
        summary=summary,
    )


def build_note_collaboration_graph(
    dataframe: pd.DataFrame,
    mention_result: CollaborationMentionResult,
    *,
    include_isolated: bool = True,
) -> CollaborationGraphResult:
    """Build the collaboration graph only from explicit employee mentions in timesheet Note."""
    prepared = _prepared_dataframe(dataframe)
    if prepared.empty:
        return _build_result_from_edges(prepared, pd.DataFrame(columns=EDGE_COLUMNS), include_isolated=include_isolated)

    evidence = mention_result.evidence_dataframe.copy()
    if evidence.empty:
        return _build_result_from_edges(prepared, pd.DataFrame(columns=EDGE_COLUMNS), include_isolated=include_isolated)

    evidence["source_employee"] = evidence["source_employee"].fillna("").astype(str).str.strip()
    evidence["target_employee"] = evidence["target_employee"].fillna("").astype(str).str.strip()
    evidence = evidence[
        evidence["source_employee"].ne("")
        & evidence["target_employee"].ne("")
        & evidence["source_employee"].ne(evidence["target_employee"])
    ].copy()
    if evidence.empty:
        return _build_result_from_edges(prepared, pd.DataFrame(columns=EDGE_COLUMNS), include_isolated=include_isolated)

    evidence["employee_a"] = evidence.apply(
        lambda row: sorted((str(row["source_employee"]), str(row["target_employee"])))[0], axis=1
    )
    evidence["employee_b"] = evidence.apply(
        lambda row: sorted((str(row["source_employee"]), str(row["target_employee"])))[1], axis=1
    )

    context = _entry_context(prepared)
    rows: list[dict[str, object]] = []
    for (employee_a, employee_b), group in evidence.groupby(["employee_a", "employee_b"], sort=True):
        entry_ids = sorted({str(value) for value in group["entry_id"].dropna().astype(str) if value})
        task_keys = sorted({str(value) for value in group["task_key"].dropna().astype(str) if value})
        projects = sorted({str(value) for value in group["project"].dropna().astype(str) if value})
        tasks = sorted(
            {
                str(context.get(entry_id, {}).get("task", "")).strip()
                for entry_id in entry_ids
                if str(context.get(entry_id, {}).get("task", "")).strip()
            }
        )
        related_hours = round(
            sum(float(context.get(entry_id, {}).get("hours", 0.0) or 0.0) for entry_id in entry_ids),
            2,
        )
        a_to_b = int(((group["source_employee"] == employee_a) & (group["target_employee"] == employee_b)).sum())
        b_to_a = int(((group["source_employee"] == employee_b) & (group["target_employee"] == employee_a)).sum())
        rows.append(
            {
                "source": employee_a,
                "target": employee_b,
                # Compatibility field consumed by existing weighted graph utilities; semantic is Note evidence count.
                "shared_task_count": int(len(group)),
                "shared_task_keys": task_keys,
                "shared_tasks": tasks,
                "projects": projects,
                "related_hours": related_hours,
                "a_to_b_count": a_to_b,
                "b_to_a_count": b_to_a,
                "evidence_entry_ids": entry_ids,
            }
        )

    edges = pd.DataFrame(rows, columns=EDGE_COLUMNS)
    if not edges.empty:
        edges = edges.sort_values(
            ["shared_task_count", "related_hours", "source", "target"],
            ascending=[False, False, True, True],
        ).reset_index(drop=True)
    return _build_result_from_edges(prepared, edges, include_isolated=include_isolated)


def apply_note_evidence_threshold(
    result: CollaborationGraphResult,
    min_evidence: int = 1,
    *,
    include_isolated: bool = False,
) -> CollaborationGraphResult:
    """Filter Note-based collaboration pairs by minimum accepted evidence and rebuild node metrics."""
    threshold = max(1, int(min_evidence))
    edges = result.edge_dataframe.copy()
    if not edges.empty:
        edges = edges[edges["shared_task_count"] >= threshold].reset_index(drop=True)
    return _build_result_from_edges(result.filtered_dataframe.copy(), edges, include_isolated=include_isolated)
