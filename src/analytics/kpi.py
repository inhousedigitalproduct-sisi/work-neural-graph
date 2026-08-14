from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from src.graph.builder import GraphBuildResult


@dataclass(frozen=True)
class AnalyticsKPI:
    total_hours: float
    active_days: int
    unique_tasks: int
    unique_employees: int
    unique_projects: int
    graph_nodes: int
    graph_edges: int
    fragmented_tasks: int
    interrupted_tasks: int
    average_context_switches: float
    average_continuity_ratio: float


def calculate_kpi_summary(
    dataframe: pd.DataFrame,
    graph_result: GraphBuildResult,
    fragmentation_dataframe: pd.DataFrame,
    context_switch_summary: pd.DataFrame,
    continuity_dataframe: pd.DataFrame,
) -> AnalyticsKPI:
    return AnalyticsKPI(
        total_hours=float(dataframe["hours"].sum()) if not dataframe.empty else 0.0,
        active_days=int(pd.to_datetime(dataframe["work_date"]).nunique()) if not dataframe.empty else 0,
        unique_tasks=int(dataframe["task_key"].nunique()) if not dataframe.empty else 0,
        unique_employees=int(dataframe["employee"].nunique()) if not dataframe.empty else 0,
        unique_projects=int(dataframe["project"].nunique()) if not dataframe.empty else 0,
        graph_nodes=graph_result.summary.nodes,
        graph_edges=graph_result.summary.edges,
        fragmented_tasks=int((fragmentation_dataframe["active_days"] > 1).sum()) if not fragmentation_dataframe.empty else 0,
        interrupted_tasks=int((fragmentation_dataframe["interruption_count"] > 0).sum())
        if not fragmentation_dataframe.empty
        else 0,
        average_context_switches=float(context_switch_summary["average_context_switches_per_active_day"].mean())
        if not context_switch_summary.empty
        else 0.0,
        average_continuity_ratio=float(continuity_dataframe["continuous_work_ratio"].mean())
        if not continuity_dataframe.empty
        else 0.0,
    )
