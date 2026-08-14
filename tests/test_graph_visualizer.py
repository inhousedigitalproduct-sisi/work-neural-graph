from __future__ import annotations

from pathlib import Path
import importlib.util

from src.domain.models import GraphStrategy
from src.graph.builder import GraphBuildConfig, GraphBuilder
from src.graph.visualizer import (
    EDGE_COLOR,
    GRAPH_BG_COLOR,
    HOVER_BG_COLOR,
    HOVER_BORDER_COLOR,
    LIGHT_FONT_COLOR,
    NODE_BORDER_COLOR,
    build_graph_figure,
)
from tests.test_graph_builder import build_graph_dataframe


def test_graph_figure_uses_dark_theme_styling() -> None:
    builder = GraphBuilder()
    result = builder.build(build_graph_dataframe(), GraphBuildConfig(strategy=GraphStrategy.SEQUENTIAL))

    figure = build_graph_figure(
        result.graph,
        result.node_dataframe,
        result.edge_dataframe,
        node_size_metric="total_hours",
        edge_width_metric="task_count",
    )

    assert figure.layout.paper_bgcolor == GRAPH_BG_COLOR
    assert figure.layout.plot_bgcolor == GRAPH_BG_COLOR
    assert figure.layout.font.color == LIGHT_FONT_COLOR
    assert figure.layout.hoverlabel.bgcolor == HOVER_BG_COLOR
    assert figure.layout.hoverlabel.bordercolor == HOVER_BORDER_COLOR
    assert figure.layout.hoverlabel.font.color == LIGHT_FONT_COLOR
    assert figure.layout.xaxis.visible is False
    assert figure.layout.yaxis.visible is False
    assert figure.layout.xaxis.showgrid is False
    assert figure.layout.yaxis.showgrid is False

    edge_trace = next(trace for trace in figure.data if trace.mode == "lines")
    assert edge_trace.line.color == EDGE_COLOR

    node_trace = next(trace for trace in figure.data if trace.mode == "markers+text")
    assert node_trace.textfont.color == LIGHT_FONT_COLOR
    assert node_trace.marker.line.color == NODE_BORDER_COLOR
    assert node_trace.marker.colorbar.tickfont.color == LIGHT_FONT_COLOR
    assert node_trace.marker.colorbar.title.font.color == LIGHT_FONT_COLOR
    assert node_trace.marker.colorbar.bgcolor == "rgba(0,0,0,0)"
    assert node_trace.marker.colorbar.orientation == "h"
    assert node_trace.marker.colorbar.title.text == "Warna node — Total jam kerja"
    assert node_trace.marker.colorbar.x == 0.5
    assert node_trace.marker.colorbar.y < 0
    assert figure.layout.margin.b >= 80


def test_graph_figure_can_hide_node_labels_for_dense_graphs() -> None:
    builder = GraphBuilder()
    result = builder.build(build_graph_dataframe(), GraphBuildConfig(strategy=GraphStrategy.SEQUENTIAL))

    figure = build_graph_figure(
        result.graph,
        result.node_dataframe,
        result.edge_dataframe,
        show_node_labels=False,
    )

    node_trace = next(
        trace
        for trace in figure.data
        if trace.mode == "markers" and getattr(trace.marker, "showscale", False)
    )
    assert node_trace.text is None


def test_neural_graph_page_imports_successfully() -> None:
    page_path = Path("pages/2_Neural_Graph.py")
    spec = importlib.util.spec_from_file_location("neural_graph_page", page_path)
    assert spec is not None
    assert spec.loader is not None


def test_graph_hover_uses_full_dates_and_activity_detail() -> None:
    builder = GraphBuilder()
    dataframe = build_graph_dataframe().copy()
    dataframe["note"] = "Detail note untuk validasi"
    result = builder.build(dataframe, GraphBuildConfig(strategy=GraphStrategy.SEQUENTIAL))

    figure = build_graph_figure(
        result.graph,
        result.node_dataframe,
        result.edge_dataframe,
        activity_dataframe=result.filtered_dataframe,
    )

    node_trace = next(trace for trace in figure.data if trace.mode == "markers+text")
    assert "01 Aug 2026" in list(node_trace.text)
    assert any("Fix Purchase Order" in row[8] for row in node_trace.customdata)
    assert "Terhubung ke" in node_trace.hovertemplate
