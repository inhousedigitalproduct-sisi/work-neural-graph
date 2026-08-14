from __future__ import annotations

from dataclasses import dataclass

from src.analytics.service import AnalyticsService, AnalyticsSnapshot
from src.llm.models import AnalysisIntent


@dataclass(frozen=True)
class DispatchResult:
    payload: dict


def execute_intent(intent: AnalysisIntent, analytics_service: AnalyticsService) -> DispatchResult:
    snapshot = analytics_service.build_snapshot(filters=_to_graph_filters(intent), strategy=_strategy_for_intent(intent))

    if intent.analysis_type == "fragmentation":
        rows = _limit_rows(
            snapshot.fragmentation,
            ["task", "project", "employees", "active_days", "calendar_span_days", "fragmentation_score"],
            intent.limit,
            intent.sort,
            "fragmentation_score",
        )
        return DispatchResult(
            payload={
                "analysis_type": intent.analysis_type,
                "summary": {
                    "total_tasks": int(snapshot.fragmentation.shape[0]),
                    "fragmented_tasks": int(snapshot.kpi.fragmented_tasks),
                },
                "rows": rows,
            }
        )

    if intent.analysis_type == "continuity":
        rows = _limit_rows(
            snapshot.continuity,
            ["task", "project", "active_days", "calendar_span_days", "continuous_work_ratio"],
            intent.limit,
            intent.sort,
            "continuous_work_ratio",
        )
        return DispatchResult(
            payload={
                "analysis_type": intent.analysis_type,
                "summary": {
                    "average_continuity_ratio": round(snapshot.kpi.average_continuity_ratio, 4),
                    "total_tasks": int(snapshot.continuity.shape[0]),
                },
                "rows": rows,
            }
        )

    if intent.analysis_type == "context_switch":
        rows = _limit_rows(
            snapshot.context_switch_daily,
            ["employee", "work_date", "unique_tasks", "unique_projects", "context_switches"],
            intent.limit,
            intent.sort,
            "context_switches",
        )
        return DispatchResult(
            payload={
                "analysis_type": intent.analysis_type,
                "summary": {
                    "average_context_switches": round(snapshot.kpi.average_context_switches, 4),
                    "employees": int(snapshot.context_switch_summary.shape[0]),
                },
                "rows": rows,
            }
        )

    if intent.analysis_type == "graph_summary":
        graph_summary = snapshot.graph_result.summary
        return DispatchResult(
            payload={
                "analysis_type": intent.analysis_type,
                "summary": {
                    "nodes": graph_summary.nodes,
                    "edges": graph_summary.edges,
                    "active_days": graph_summary.active_days,
                    "graph_density": round(graph_summary.density, 4),
                    "average_degree": round(graph_summary.average_degree, 4),
                },
                "rows": [],
            }
        )

    if intent.analysis_type == "project_comparison":
        project_rows = snapshot.filtered_dataframe.groupby("project", as_index=False).agg(
            total_hours=("hours", "sum"),
            unique_tasks=("task_key", "nunique"),
            unique_employees=("employee", "nunique"),
        )
        fragmentation_by_project = (
            snapshot.fragmentation.groupby("project", as_index=False)
            .agg(
                fragmented_tasks=("active_days", lambda values: int(sum(value > 1 for value in values))),
                average_fragmentation_score=("fragmentation_score", "mean"),
                average_continuity_ratio=("continuous_work_ratio", "mean"),
            )
        )
        merged = project_rows.merge(fragmentation_by_project, on="project", how="left").fillna(0)
        rows = _limit_rows(
            merged,
            [
                "project",
                "total_hours",
                "unique_tasks",
                "unique_employees",
                "fragmented_tasks",
                "average_fragmentation_score",
                "average_continuity_ratio",
            ],
            intent.limit,
            intent.sort,
            "average_fragmentation_score",
        )
        return DispatchResult(
            payload={
                "analysis_type": intent.analysis_type,
                "summary": {"projects": int(merged.shape[0])},
                "rows": rows,
            }
        )

    if intent.analysis_type == "task_summary":
        rows = _limit_rows(
            snapshot.fragmentation,
            [
                "task",
                "project",
                "employees",
                "total_hours",
                "active_days",
                "fragmentation_score",
                "continuous_work_ratio",
            ],
            intent.limit,
            intent.sort,
            "total_hours" if intent.metric == "total_hours" else "fragmentation_score",
        )
        return DispatchResult(
            payload={
                "analysis_type": intent.analysis_type,
                "summary": {"tasks": int(snapshot.fragmentation.shape[0])},
                "rows": rows,
            }
        )

    raise ValueError(f"Unsupported analysis type: {intent.analysis_type}")


def _limit_rows(snapshot_dataframe, columns: list[str], limit: int, sort: str, sort_by: str) -> list[dict]:
    ascending = sort == "asc"
    subset = snapshot_dataframe.copy()
    if sort_by in subset.columns:
        subset = subset.sort_values(sort_by, ascending=ascending)
    subset = subset[columns].head(limit).copy()
    for column in subset.columns:
        if str(subset[column].dtype).startswith("datetime"):
            subset[column] = subset[column].dt.date.astype(str)
    return subset.to_dict(orient="records")


def _to_graph_filters(intent: AnalysisIntent):
    from src.graph.builder import GraphFilterConfig

    return GraphFilterConfig(
        employee_names=tuple(intent.filters.employees or ()),
        projects=tuple(intent.filters.projects or ()),
        task_keys=tuple(intent.filters.tasks or ()),
        start_date=intent.filters.start_date.isoformat() if intent.filters.start_date else None,
        end_date=intent.filters.end_date.isoformat() if intent.filters.end_date else None,
    )


def _strategy_for_intent(intent: AnalysisIntent):
    from src.domain.models import GraphStrategy

    return GraphStrategy.SEQUENTIAL
