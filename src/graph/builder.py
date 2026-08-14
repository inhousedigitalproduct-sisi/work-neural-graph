from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations

import networkx as nx
import pandas as pd

from src.domain.models import GraphStrategy


@dataclass(frozen=True)
class GraphFilterConfig:
    employee_names: tuple[str, ...] = ()
    projects: tuple[str, ...] = ()
    task_keys: tuple[str, ...] = ()
    states: tuple[str, ...] = ()
    note_keyword: str | None = None
    start_date: str | None = None
    end_date: str | None = None


@dataclass(frozen=True)
class GraphBuildConfig:
    strategy: GraphStrategy = GraphStrategy.SEQUENTIAL


@dataclass(frozen=True)
class GraphSummary:
    nodes: int
    edges: int
    active_days: int
    unique_tasks: int
    total_hours: float
    average_degree: float
    connected_components: int
    density: float


@dataclass(frozen=True)
class GraphBuildResult:
    filtered_dataframe: pd.DataFrame
    node_dataframe: pd.DataFrame
    relationship_dataframe: pd.DataFrame
    edge_dataframe: pd.DataFrame
    graph: nx.Graph
    summary: GraphSummary


def apply_graph_filters(dataframe: pd.DataFrame, filters: GraphFilterConfig) -> pd.DataFrame:
    if dataframe.empty:
        return dataframe.copy()

    filtered = dataframe.copy()
    filtered["work_date"] = pd.to_datetime(filtered["work_date"])

    if filters.employee_names:
        filtered = filtered[filtered["employee"].isin(filters.employee_names)]
    if filters.projects:
        filtered = filtered[filtered["project"].isin(filters.projects)]
    if filters.task_keys:
        filtered = filtered[filtered["task_key"].isin(filters.task_keys)]
    if filters.states and "state" in filtered.columns:
        filtered = filtered[filtered["state"].fillna("").isin(filters.states)]
    if filters.note_keyword and "note" in filtered.columns:
        filtered = filtered[
            filtered["note"].fillna("").str.contains(filters.note_keyword, case=False, na=False)
        ]
    if filters.start_date:
        filtered = filtered[filtered["work_date"] >= pd.to_datetime(filters.start_date)]
    if filters.end_date:
        filtered = filtered[filtered["work_date"] <= pd.to_datetime(filters.end_date)]

    return filtered.reset_index(drop=True)


class GraphBuilder:
    def build(self, dataframe: pd.DataFrame, config: GraphBuildConfig) -> GraphBuildResult:
        prepared = self._prepare_dataframe(dataframe)
        node_dataframe = self._build_node_dataframe(prepared)
        relationship_dataframe = self._build_relationships(prepared, config.strategy)
        edge_dataframe = self._aggregate_edges(relationship_dataframe)
        graph = self._build_networkx_graph(node_dataframe, edge_dataframe)
        node_dataframe = self._apply_graph_node_metrics(node_dataframe, graph)
        summary = self._build_summary(prepared, graph)
        return GraphBuildResult(
            filtered_dataframe=prepared,
            node_dataframe=node_dataframe,
            relationship_dataframe=relationship_dataframe,
            edge_dataframe=edge_dataframe,
            graph=graph,
            summary=summary,
        )

    def _prepare_dataframe(self, dataframe: pd.DataFrame) -> pd.DataFrame:
        if dataframe.empty:
            return pd.DataFrame(
                columns=["entry_id", "employee", "work_date", "project", "task", "task_key", "hours"]
            )

        prepared = dataframe.copy()
        prepared["work_date"] = pd.to_datetime(prepared["work_date"])
        prepared["hours"] = prepared["hours"].astype(float)
        return prepared.sort_values(["work_date", "employee", "project", "task"]).reset_index(drop=True)

    def _build_node_dataframe(self, dataframe: pd.DataFrame) -> pd.DataFrame:
        if dataframe.empty:
            return pd.DataFrame(
                columns=[
                    "date",
                    "total_hours",
                    "unique_tasks",
                    "unique_employees",
                    "unique_projects",
                    "employees",
                    "incoming_relationships",
                    "outgoing_relationships",
                    "degree",
                ]
            )

        node_dataframe = (
            dataframe.groupby("work_date", as_index=False)
            .agg(
                total_hours=("hours", "sum"),
                unique_tasks=("task_key", "nunique"),
                unique_employees=("employee", "nunique"),
                unique_projects=("project", "nunique"),
                employees=("employee", lambda values: sorted(set(values))),
            )
            .rename(columns={"work_date": "date"})
        )
        node_dataframe["date"] = pd.to_datetime(node_dataframe["date"])
        node_dataframe["incoming_relationships"] = 0
        node_dataframe["outgoing_relationships"] = 0
        node_dataframe["degree"] = 0
        return node_dataframe

    def _build_relationships(
        self,
        dataframe: pd.DataFrame,
        strategy: GraphStrategy,
    ) -> pd.DataFrame:
        if dataframe.empty:
            return pd.DataFrame(
                columns=[
                    "source_date",
                    "target_date",
                    "task_key",
                    "task",
                    "project",
                    "employees",
                    "source_hours",
                    "target_hours",
                    "related_hours",
                    "gap_days",
                    "interruption_days",
                ]
            )

        task_date_rollup = (
            dataframe.groupby(["task_key", "work_date"], as_index=False)
            .agg(
                task=("task", "first"),
                project=("project", "first"),
                employees=("employee", lambda values: sorted(set(values))),
                hours=("hours", "sum"),
            )
            .sort_values(["task_key", "work_date"])
        )

        relationships: list[dict[str, object]] = []
        for task_key, group in task_date_rollup.groupby("task_key", sort=False):
            dates = group["work_date"].tolist()
            if len(dates) < 2:
                continue

            if strategy == GraphStrategy.SEQUENTIAL:
                pairs = zip(range(len(dates) - 1), range(1, len(dates)))
            else:
                pairs = combinations(range(len(dates)), 2)

            for source_index, target_index in pairs:
                source_row = group.iloc[source_index]
                target_row = group.iloc[target_index]
                gap_days = int((target_row["work_date"] - source_row["work_date"]).days)
                relationships.append(
                    {
                        "source_date": source_row["work_date"],
                        "target_date": target_row["work_date"],
                        "task_key": task_key,
                        "task": source_row["task"],
                        "project": source_row["project"],
                        "employees": sorted(set(source_row["employees"]) | set(target_row["employees"])),
                        "source_hours": float(source_row["hours"]),
                        "target_hours": float(target_row["hours"]),
                        "related_hours": float(source_row["hours"]) + float(target_row["hours"]),
                        "gap_days": gap_days,
                        "interruption_days": max(gap_days - 1, 0),
                    }
                )

        return pd.DataFrame(relationships)

    def _aggregate_edges(self, relationship_dataframe: pd.DataFrame) -> pd.DataFrame:
        if relationship_dataframe.empty:
            return pd.DataFrame(
                columns=[
                    "source",
                    "target",
                    "task_count",
                    "shared_tasks",
                    "task_keys",
                    "employees",
                    "projects",
                    "related_hours",
                    "gap_days",
                    "interruption_days",
                ]
            )

        edge_rows: list[dict[str, object]] = []
        grouped = relationship_dataframe.groupby(["source_date", "target_date"], sort=True)
        for (source_date, target_date), group in grouped:
            edge_rows.append(
                {
                    "source": pd.to_datetime(source_date),
                    "target": pd.to_datetime(target_date),
                    "task_count": int(group["task_key"].nunique()),
                    "shared_tasks": sorted(set(group["task"])),
                    "task_keys": sorted(set(group["task_key"])),
                    "employees": sorted({employee for employees in group["employees"] for employee in employees}),
                    "projects": sorted(set(group["project"])),
                    "related_hours": float(group["related_hours"].sum()),
                    "gap_days": int(group["gap_days"].iloc[0]),
                    "interruption_days": int(group["interruption_days"].iloc[0]),
                }
            )

        return pd.DataFrame(edge_rows).sort_values(["source", "target"]).reset_index(drop=True)

    def _build_networkx_graph(self, node_dataframe: pd.DataFrame, edge_dataframe: pd.DataFrame) -> nx.Graph:
        graph = nx.Graph()

        for node in node_dataframe.to_dict(orient="records"):
            graph.add_node(
                node["date"].date().isoformat(),
                **{
                    "date": node["date"].date().isoformat(),
                    "total_hours": float(node["total_hours"]),
                    "unique_tasks": int(node["unique_tasks"]),
                    "unique_employees": int(node["unique_employees"]),
                    "unique_projects": int(node["unique_projects"]),
                    "incoming_relationships": int(node["incoming_relationships"]),
                    "outgoing_relationships": int(node["outgoing_relationships"]),
                    "degree": int(node["degree"]),
                },
            )

        for edge in edge_dataframe.to_dict(orient="records"):
            graph.add_edge(
                edge["source"].date().isoformat(),
                edge["target"].date().isoformat(),
                **{
                    "task_count": int(edge["task_count"]),
                    "shared_tasks": edge["shared_tasks"],
                    "task_keys": edge["task_keys"],
                    "employees": edge["employees"],
                    "projects": edge["projects"],
                    "related_hours": float(edge["related_hours"]),
                    "gap_days": int(edge["gap_days"]),
                    "interruption_days": int(edge["interruption_days"]),
                },
            )

        for node_name in list(graph.nodes):
            graph.nodes[node_name]["degree"] = int(graph.degree[node_name])
            graph.nodes[node_name]["incoming_relationships"] = int(graph.degree[node_name])
            graph.nodes[node_name]["outgoing_relationships"] = int(graph.degree[node_name])

        return graph

    def _apply_graph_node_metrics(self, node_dataframe: pd.DataFrame, graph: nx.Graph) -> pd.DataFrame:
        if node_dataframe.empty:
            return node_dataframe

        updated = node_dataframe.copy()
        updated["date_key"] = updated["date"].dt.date.astype(str)
        updated["degree"] = updated["date_key"].map(lambda key: int(graph.degree[key]) if key in graph else 0)
        updated["incoming_relationships"] = updated["degree"]
        updated["outgoing_relationships"] = updated["degree"]
        return updated.drop(columns=["date_key"])

    def _build_summary(self, dataframe: pd.DataFrame, graph: nx.Graph) -> GraphSummary:
        node_count = graph.number_of_nodes()
        edge_count = graph.number_of_edges()
        average_degree = (sum(dict(graph.degree()).values()) / node_count) if node_count else 0.0
        connected_components = nx.number_connected_components(graph) if node_count else 0
        density = nx.density(graph) if node_count > 1 else 0.0

        return GraphSummary(
            nodes=node_count,
            edges=edge_count,
            active_days=node_count,
            unique_tasks=int(dataframe["task_key"].nunique()) if not dataframe.empty else 0,
            total_hours=float(dataframe["hours"].sum()) if not dataframe.empty else 0.0,
            average_degree=float(average_degree),
            connected_components=int(connected_components),
            density=float(density),
        )
