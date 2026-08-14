from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from src.analytics.concurrency import analyze_concurrency
from src.analytics.continuity import analyze_continuity
from src.analytics.context_switch import analyze_context_switching
from src.analytics.fragmentation import analyze_fragmentation
from src.analytics.kpi import AnalyticsKPI, calculate_kpi_summary
from src.domain.models import GraphStrategy
from src.graph.builder import GraphBuildResult, GraphFilterConfig
from src.services import GraphService


@dataclass(frozen=True)
class AnalyticsSnapshot:
    filtered_dataframe: pd.DataFrame
    fragmentation: pd.DataFrame
    continuity: pd.DataFrame
    context_switch_daily: pd.DataFrame
    context_switch_summary: pd.DataFrame
    concurrency: dict[str, pd.DataFrame]
    graph_result: GraphBuildResult
    kpi: AnalyticsKPI


class AnalyticsService:
    def __init__(self, db_path: Path) -> None:
        self.graph_service = GraphService(db_path)

    def build_snapshot(
        self,
        filters: GraphFilterConfig,
        strategy: GraphStrategy = GraphStrategy.SEQUENTIAL,
    ) -> AnalyticsSnapshot:
        graph_result = self.graph_service.build_graph(filters=filters, strategy=strategy)
        filtered_dataframe = graph_result.filtered_dataframe.copy()
        fragmentation = analyze_fragmentation(filtered_dataframe)
        continuity = analyze_continuity(filtered_dataframe)
        context_daily, context_summary = analyze_context_switching(filtered_dataframe)
        concurrency = analyze_concurrency(filtered_dataframe)
        kpi = calculate_kpi_summary(
            filtered_dataframe,
            graph_result,
            fragmentation,
            context_summary,
            continuity,
        )
        return AnalyticsSnapshot(
            filtered_dataframe=filtered_dataframe,
            fragmentation=fragmentation,
            continuity=continuity,
            context_switch_daily=context_daily,
            context_switch_summary=context_summary,
            concurrency=concurrency,
            graph_result=graph_result,
            kpi=kpi,
        )
