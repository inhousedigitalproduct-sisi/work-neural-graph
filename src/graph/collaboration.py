from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations

import networkx as nx
import pandas as pd


@dataclass(frozen=True)
class CollaborationSummary:
    employees: int
    collaboration_links: int
    collaborative_tasks: int
    projects: int
    collaborative_hours: float
    average_collaborators: float


@dataclass(frozen=True)
class CollaborationGraphResult:
    filtered_dataframe: pd.DataFrame
    node_dataframe: pd.DataFrame
    edge_dataframe: pd.DataFrame
    graph: nx.Graph
    summary: CollaborationSummary


def build_collaboration_graph(dataframe: pd.DataFrame) -> CollaborationGraphResult:
    """Build an employee collaboration graph from shared task keys, independent of date."""
    prepared = dataframe.copy()
    if prepared.empty:
        empty_nodes = pd.DataFrame(
            columns=[
                "employee",
                "collaborator_count",
                "collaborative_task_count",
                "project_count",
                "collaborative_hours",
                "collaborators",
                "top_collaborators",
                "top_tasks",
            ]
        )
        empty_edges = pd.DataFrame(
            columns=["source", "target", "shared_task_count", "shared_tasks", "projects", "related_hours"]
        )
        return CollaborationGraphResult(
            filtered_dataframe=prepared,
            node_dataframe=empty_nodes,
            edge_dataframe=empty_edges,
            graph=nx.Graph(),
            summary=CollaborationSummary(0, 0, 0, 0, 0.0, 0.0),
        )

    required = {"employee", "task_key", "task", "project", "hours"}
    missing = required - set(prepared.columns)
    if missing:
        raise ValueError(f"Missing columns for collaboration graph: {', '.join(sorted(missing))}")

    prepared["employee"] = prepared["employee"].fillna("").astype(str).str.strip()
    prepared = prepared[prepared["employee"].ne("")].copy()
    prepared["hours"] = pd.to_numeric(prepared["hours"], errors="coerce").fillna(0.0)

    edge_records: list[dict[str, object]] = []
    collaborative_task_keys: set[str] = set()
    employee_collaborative_tasks: dict[str, set[str]] = {}

    for task_key, group in prepared.groupby("task_key", sort=False):
        employees = sorted(group["employee"].dropna().astype(str).unique().tolist())
        if len(employees) < 2:
            continue

        collaborative_task_keys.add(str(task_key))
        task_name = next((str(value) for value in group["task"].tolist() if pd.notna(value) and str(value).strip()), str(task_key))
        projects = sorted(group["project"].dropna().astype(str).unique().tolist())

        for employee in employees:
            employee_collaborative_tasks.setdefault(employee, set()).add(str(task_key))

        for source, target in combinations(employees, 2):
            pair_rows = group[group["employee"].isin([source, target])]
            edge_records.append(
                {
                    "source": source,
                    "target": target,
                    "task_key": str(task_key),
                    "task": task_name,
                    "projects": projects,
                    "related_hours": float(pair_rows["hours"].sum()),
                }
            )

    if edge_records:
        raw_edges = pd.DataFrame(edge_records)
        rows: list[dict[str, object]] = []
        for (source, target), group in raw_edges.groupby(["source", "target"], sort=True):
            rows.append(
                {
                    "source": source,
                    "target": target,
                    "shared_task_count": int(group["task_key"].nunique()),
                    "shared_tasks": sorted(set(group["task"].astype(str))),
                    "projects": sorted({project for projects in group["projects"] for project in projects}),
                    "related_hours": round(float(group["related_hours"].sum()), 2),
                }
            )
        edge_dataframe = pd.DataFrame(rows).sort_values(
            ["shared_task_count", "related_hours", "source", "target"], ascending=[False, False, True, True]
        ).reset_index(drop=True)
    else:
        edge_dataframe = pd.DataFrame(
            columns=["source", "target", "shared_task_count", "shared_tasks", "projects", "related_hours"]
        )

    graph = nx.Graph()
    for employee in sorted(prepared["employee"].unique().tolist()):
        graph.add_node(employee)
    for edge in edge_dataframe.to_dict(orient="records"):
        graph.add_edge(
            edge["source"],
            edge["target"],
            shared_task_count=int(edge["shared_task_count"]),
            shared_tasks=edge["shared_tasks"],
            projects=edge["projects"],
            related_hours=float(edge["related_hours"]),
        )

    node_rows: list[dict[str, object]] = []
    for employee in sorted(graph.nodes):
        task_keys = employee_collaborative_tasks.get(employee, set())
        employee_rows = prepared[prepared["employee"] == employee]
        collaborative_rows = employee_rows[employee_rows["task_key"].astype(str).isin(task_keys)]
        collaborators = sorted(graph.neighbors(employee))
        collaborator_strength = []
        for collaborator in collaborators:
            data = graph.get_edge_data(employee, collaborator) or {}
            collaborator_strength.append((collaborator, int(data.get("shared_task_count", 0))))
        collaborator_strength.sort(key=lambda item: (-item[1], item[0]))
        top_collaborators = [f"{name} ({count} task)" for name, count in collaborator_strength[:5]]
        top_tasks = (
            collaborative_rows["task"].fillna("").astype(str).value_counts().head(5).index.tolist()
            if not collaborative_rows.empty
            else []
        )
        node_rows.append(
            {
                "employee": employee,
                "collaborator_count": int(graph.degree[employee]),
                "collaborative_task_count": int(len(task_keys)),
                "project_count": int(collaborative_rows["project"].dropna().nunique()),
                "collaborative_hours": round(float(collaborative_rows["hours"].sum()), 2),
                "collaborators": collaborators,
                "top_collaborators": top_collaborators,
                "top_tasks": top_tasks,
            }
        )
    node_dataframe = pd.DataFrame(node_rows)

    degrees = [degree for _, degree in graph.degree()]
    summary = CollaborationSummary(
        employees=int(graph.number_of_nodes()),
        collaboration_links=int(graph.number_of_edges()),
        collaborative_tasks=int(len(collaborative_task_keys)),
        projects=int(prepared[prepared["task_key"].astype(str).isin(collaborative_task_keys)]["project"].dropna().nunique()),
        collaborative_hours=round(
            float(prepared[prepared["task_key"].astype(str).isin(collaborative_task_keys)]["hours"].sum()), 2
        ),
        average_collaborators=round(float(sum(degrees) / len(degrees)), 2) if degrees else 0.0,
    )
    return CollaborationGraphResult(prepared, node_dataframe, edge_dataframe, graph, summary)
