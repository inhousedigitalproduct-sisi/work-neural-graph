from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations

import networkx as nx
import pandas as pd


EDGE_COLUMNS = [
    "source",
    "target",
    "shared_task_count",
    "shared_task_keys",
    "shared_tasks",
    "projects",
    "related_hours",
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


def _empty_result(prepared: pd.DataFrame) -> CollaborationGraphResult:
    return CollaborationGraphResult(
        filtered_dataframe=prepared,
        node_dataframe=pd.DataFrame(columns=NODE_COLUMNS),
        edge_dataframe=pd.DataFrame(columns=EDGE_COLUMNS),
        graph=nx.Graph(),
        summary=CollaborationSummary(0, 0, 0, 0, 0.0, 0.0),
    )


def _build_result_from_edges(
    prepared: pd.DataFrame,
    edge_dataframe: pd.DataFrame,
    *,
    include_isolated: bool,
) -> CollaborationGraphResult:
    graph = nx.Graph()
    all_employees = sorted(prepared["employee"].dropna().astype(str).unique().tolist())

    if include_isolated:
        graph.add_nodes_from(all_employees)

    for edge in edge_dataframe.to_dict(orient="records"):
        source = str(edge["source"])
        target = str(edge["target"])
        graph.add_edge(
            source,
            target,
            shared_task_count=int(edge["shared_task_count"]),
            shared_task_keys=list(edge.get("shared_task_keys", []) or []),
            shared_tasks=list(edge.get("shared_tasks", []) or []),
            projects=list(edge.get("projects", []) or []),
            related_hours=float(edge.get("related_hours", 0.0)),
        )

    node_rows: list[dict[str, object]] = []
    for employee in sorted(graph.nodes):
        collaborators = sorted(graph.neighbors(employee))
        active_task_keys: set[str] = set()
        collaborator_strength: list[tuple[str, int]] = []
        for collaborator in collaborators:
            data = graph.get_edge_data(employee, collaborator) or {}
            active_task_keys.update(str(value) for value in data.get("shared_task_keys", []) if value)
            collaborator_strength.append((collaborator, int(data.get("shared_task_count", 0))))

        collaborator_strength.sort(key=lambda item: (-item[1], item[0]))
        top_collaborators = [f"{name} ({count} task)" for name, count in collaborator_strength[:5]]

        employee_rows = prepared[prepared["employee"] == employee]
        collaborative_rows = employee_rows[
            employee_rows["task_key"].astype(str).isin(active_task_keys)
        ]
        top_tasks = (
            collaborative_rows["task"].fillna("").astype(str).value_counts().head(5).index.tolist()
            if not collaborative_rows.empty
            else []
        )
        node_rows.append(
            {
                "employee": employee,
                "collaborator_count": int(graph.degree[employee]),
                "collaborative_task_count": int(len(active_task_keys)),
                "project_count": int(collaborative_rows["project"].dropna().nunique()),
                "collaborative_hours": round(float(collaborative_rows["hours"].sum()), 2),
                "collaborators": collaborators,
                "top_collaborators": top_collaborators,
                "top_tasks": top_tasks,
            }
        )

    node_dataframe = pd.DataFrame(node_rows, columns=NODE_COLUMNS)
    active_task_keys = {
        str(task_key)
        for values in edge_dataframe.get("shared_task_keys", pd.Series(dtype=object)).tolist()
        for task_key in (values or [])
    }
    visible_employees = set(graph.nodes)
    collaborative_rows = prepared[
        prepared["task_key"].astype(str).isin(active_task_keys)
        & prepared["employee"].isin(visible_employees)
    ]
    degrees = [degree for _, degree in graph.degree()]
    summary = CollaborationSummary(
        employees=int(graph.number_of_nodes()),
        collaboration_links=int(graph.number_of_edges()),
        collaborative_tasks=int(len(active_task_keys)),
        projects=int(collaborative_rows["project"].dropna().nunique()) if not collaborative_rows.empty else 0,
        collaborative_hours=round(float(collaborative_rows["hours"].sum()), 2) if not collaborative_rows.empty else 0.0,
        average_collaborators=round(float(sum(degrees) / len(degrees)), 2) if degrees else 0.0,
    )
    return CollaborationGraphResult(
        filtered_dataframe=prepared,
        node_dataframe=node_dataframe,
        edge_dataframe=edge_dataframe.reset_index(drop=True),
        graph=graph,
        summary=summary,
    )


def build_collaboration_graph(dataframe: pd.DataFrame) -> CollaborationGraphResult:
    """Build an employee collaboration graph from shared task keys, independent of date."""
    prepared = dataframe.copy()
    if prepared.empty:
        return _empty_result(prepared)

    required = {"employee", "task_key", "task", "project", "hours"}
    missing = required - set(prepared.columns)
    if missing:
        raise ValueError(f"Missing columns for collaboration graph: {', '.join(sorted(missing))}")

    prepared["employee"] = prepared["employee"].fillna("").astype(str).str.strip()
    prepared = prepared[prepared["employee"].ne("")].copy()
    prepared["hours"] = pd.to_numeric(prepared["hours"], errors="coerce").fillna(0.0)

    edge_records: list[dict[str, object]] = []
    for task_key, group in prepared.groupby("task_key", sort=False):
        employees = sorted(group["employee"].dropna().astype(str).unique().tolist())
        if len(employees) < 2:
            continue

        task_name = next(
            (str(value) for value in group["task"].tolist() if pd.notna(value) and str(value).strip()),
            str(task_key),
        )
        projects = sorted(group["project"].dropna().astype(str).unique().tolist())

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
                    "shared_task_keys": sorted(set(group["task_key"].astype(str))),
                    "shared_tasks": sorted(set(group["task"].astype(str))),
                    "projects": sorted({project for projects in group["projects"] for project in projects}),
                    "related_hours": round(float(group["related_hours"].sum()), 2),
                }
            )
        edge_dataframe = pd.DataFrame(rows, columns=EDGE_COLUMNS).sort_values(
            ["shared_task_count", "related_hours", "source", "target"],
            ascending=[False, False, True, True],
        ).reset_index(drop=True)
    else:
        edge_dataframe = pd.DataFrame(columns=EDGE_COLUMNS)

    return _build_result_from_edges(prepared, edge_dataframe, include_isolated=True)


def apply_collaboration_threshold(
    result: CollaborationGraphResult,
    min_shared_tasks: int = 1,
    *,
    include_isolated: bool = False,
) -> CollaborationGraphResult:
    """Apply the visible shared-task threshold and rebuild graph/node metrics consistently."""
    threshold = max(1, int(min_shared_tasks))
    edges = result.edge_dataframe.copy()
    if not edges.empty:
        edges = edges[edges["shared_task_count"] >= threshold].reset_index(drop=True)
    return _build_result_from_edges(
        result.filtered_dataframe.copy(),
        edges,
        include_isolated=include_isolated,
    )


def build_ranked_collaborators(node_dataframe: pd.DataFrame, *, limit: int = 10) -> pd.DataFrame:
    """Rank active employees by breadth first, then shared-task intensity and hours."""
    if node_dataframe.empty:
        return pd.DataFrame(columns=["employee", "collaborator_count", "collaborative_task_count", "collaborative_hours", "project_count"])
    columns = ["employee", "collaborator_count", "collaborative_task_count", "collaborative_hours", "project_count"]
    return node_dataframe[columns].sort_values(
        ["collaborator_count", "collaborative_task_count", "collaborative_hours", "project_count", "employee"],
        ascending=[False, False, False, False, True],
    ).head(max(1, int(limit))).reset_index(drop=True)


def build_strongest_pairs(edge_dataframe: pd.DataFrame, *, limit: int = 10) -> pd.DataFrame:
    """Return the strongest currently visible collaboration pairs."""
    if edge_dataframe.empty:
        return pd.DataFrame(columns=["source", "target", "shared_task_count", "related_hours", "projects", "shared_tasks"])
    columns = ["source", "target", "shared_task_count", "related_hours", "projects", "shared_tasks"]
    return edge_dataframe[columns].sort_values(
        ["shared_task_count", "related_hours", "source", "target"],
        ascending=[False, False, True, True],
    ).head(max(1, int(limit))).reset_index(drop=True)


def build_key_connectors(graph: nx.Graph, *, limit: int = 10) -> pd.DataFrame:
    """Rank bridge people using weighted betweenness centrality (stronger edges = shorter paths)."""
    if graph.number_of_nodes() == 0:
        return pd.DataFrame(columns=["employee", "connector_score", "collaborator_count"])

    weighted = graph.copy()
    for source, target, data in weighted.edges(data=True):
        strength = max(float(data.get("shared_task_count", 1) or 1), 1.0)
        weighted[source][target]["distance"] = 1.0 / strength
    scores = nx.betweenness_centrality(weighted, weight="distance", normalized=True)
    rows = [
        {
            "employee": employee,
            "connector_score": round(float(score), 4),
            "collaborator_count": int(graph.degree[employee]),
        }
        for employee, score in scores.items()
    ]
    return pd.DataFrame(rows).sort_values(
        ["connector_score", "collaborator_count", "employee"],
        ascending=[False, False, True],
    ).head(max(1, int(limit))).reset_index(drop=True)


def build_low_connectivity(node_dataframe: pd.DataFrame, *, limit: int = 10) -> pd.DataFrame:
    """Return employees with the weakest graph connectivity; this is not a performance score."""
    if node_dataframe.empty:
        return pd.DataFrame(columns=["employee", "collaborator_count", "collaborative_task_count", "project_count"])
    columns = ["employee", "collaborator_count", "collaborative_task_count", "project_count"]
    ordered = node_dataframe[columns].sort_values(
        ["collaborator_count", "collaborative_task_count", "project_count", "employee"],
        ascending=[True, True, True, True],
    )
    low = ordered[ordered["collaborator_count"] <= 1]
    if low.empty:
        low = ordered
    return low.head(max(1, int(limit))).reset_index(drop=True)


def build_collaboration_clusters(graph: nx.Graph) -> pd.DataFrame:
    """Describe collaboration communities already implicit in the network topology."""
    connected = graph.subgraph([node for node, degree in graph.degree() if degree > 0]).copy()
    if connected.number_of_nodes() == 0:
        return pd.DataFrame(columns=["cluster", "size", "members", "internal_links", "shared_task_strength"])

    try:
        communities = [
            set(group)
            for group in nx.community.greedy_modularity_communities(
                connected,
                weight="shared_task_count",
            )
        ]
    except Exception:
        communities = [set(component) for component in nx.connected_components(connected)]

    communities.sort(key=lambda group: (-len(group), sorted(group)[0] if group else ""))
    rows: list[dict[str, object]] = []
    for index, members in enumerate(communities, start=1):
        subgraph = connected.subgraph(members)
        strength = sum(int(data.get("shared_task_count", 0)) for _, _, data in subgraph.edges(data=True))
        rows.append(
            {
                "cluster": index,
                "size": len(members),
                "members": sorted(members),
                "internal_links": int(subgraph.number_of_edges()),
                "shared_task_strength": int(strength),
            }
        )
    return pd.DataFrame(rows)
