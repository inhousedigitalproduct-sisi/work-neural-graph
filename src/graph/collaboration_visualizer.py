from __future__ import annotations

from collections.abc import Sequence

import networkx as nx
import pandas as pd
import plotly.graph_objects as go

GRAPH_BG_COLOR = "#000000"
LIGHT_FONT_COLOR = "#FFFFFF"
EDGE_COLOR = "rgba(255,255,255,0.72)"
NODE_BORDER_COLOR = "rgba(255,255,255,0.65)"


def _scale(values: Sequence[float], minimum: float, maximum: float) -> list[float]:
    values = [float(value) for value in values]
    if not values:
        return []
    low, high = min(values), max(values)
    if low == high:
        return [(minimum + maximum) / 2 for _ in values]
    return [minimum + ((value - low) / (high - low)) * (maximum - minimum) for value in values]


def _join(values: object, limit: int = 5) -> str:
    if not isinstance(values, list) or not values:
        return "-"
    return ", ".join(str(value) for value in values[:limit])


def build_collaboration_figure(
    graph: nx.Graph,
    node_dataframe: pd.DataFrame,
    edge_dataframe: pd.DataFrame,
    node_size_metric: str = "collaborator_count",
    edge_width_metric: str = "shared_task_count",
    show_node_labels: bool = True,
) -> go.Figure:
    figure = go.Figure()
    if graph.number_of_nodes() == 0:
        figure.update_layout(
            height=720,
            paper_bgcolor=GRAPH_BG_COLOR,
            plot_bgcolor=GRAPH_BG_COLOR,
            font={"color": LIGHT_FONT_COLOR},
            xaxis={"visible": False},
            yaxis={"visible": False},
        )
        return figure

    positions = nx.spring_layout(graph, seed=42)
    widths = _scale(edge_dataframe[edge_width_metric].tolist(), 1.5, 8.0) if not edge_dataframe.empty else []
    for index, edge in enumerate(edge_dataframe.to_dict(orient="records")):
        source, target = edge["source"], edge["target"]
        x0, y0 = positions[source]
        x1, y1 = positions[target]
        figure.add_trace(
            go.Scatter(
                x=[x0, x1], y=[y0, y1], mode="lines",
                line={"width": widths[index], "color": EDGE_COLOR},
                hoverinfo="skip", showlegend=False,
            )
        )
        figure.add_trace(
            go.Scatter(
                x=[(x0 + x1) / 2], y=[(y0 + y1) / 2], mode="markers",
                marker={"size": max(widths[index] + 6, 10), "color": "rgba(0,0,0,0)"},
                customdata=[[source, target, int(edge["shared_task_count"]), _join(edge["shared_tasks"]), _join(edge["projects"]), round(float(edge["related_hours"]), 2)]],
                hovertemplate=(
                    "<b>%{customdata[0]} ↔ %{customdata[1]}</b><br>"
                    "<b>Task bersama:</b> %{customdata[2]}<br>"
                    "<b>Task:</b> %{customdata[3]}<br>"
                    "<b>Project:</b> %{customdata[4]}<br>"
                    "<b>Total jam terkait:</b> %{customdata[5]}<extra></extra>"
                ),
                showlegend=False,
            )
        )

    sizes = _scale(node_dataframe[node_size_metric].tolist(), 20, 54)
    metric_labels = {
        "collaborator_count": "Jumlah kolaborator",
        "collaborative_task_count": "Task kolaboratif",
        "project_count": "Project kolaboratif",
        "collaborative_hours": "Jam kolaboratif",
    }
    node_x, node_y, labels, customdata = [], [], [], []
    for node in node_dataframe.to_dict(orient="records"):
        employee = node["employee"]
        x, y = positions[employee]
        node_x.append(x)
        node_y.append(y)
        labels.append(employee)
        customdata.append([
            employee,
            int(node["collaborator_count"]),
            int(node["collaborative_task_count"]),
            int(node["project_count"]),
            round(float(node["collaborative_hours"]), 2),
            _join(node.get("top_collaborators", [])),
            _join(node.get("top_tasks", [])),
        ])

    figure.add_trace(
        go.Scatter(
            x=node_x, y=node_y,
            mode="markers+text" if show_node_labels else "markers",
            text=labels if show_node_labels else None,
            textposition="top center",
            textfont={"color": LIGHT_FONT_COLOR},
            marker={
                "size": sizes,
                "color": node_dataframe[node_size_metric].tolist(),
                "colorscale": "YlGnBu",
                "line": {"width": 1, "color": NODE_BORDER_COLOR},
                "showscale": True,
                "colorbar": {
                    "orientation": "h", "x": 0.5, "xanchor": "center", "y": -0.12,
                    "len": 0.52, "thickness": 14,
                    "title": {"text": metric_labels.get(node_size_metric, node_size_metric), "side": "top"},
                },
            },
            customdata=customdata,
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>"
                "<b>Kolaborator:</b> %{customdata[1]} orang<br>"
                "<b>Task kolaboratif:</b> %{customdata[2]}<br>"
                "<b>Project terkait:</b> %{customdata[3]}<br>"
                "<b>Jam pada task kolaboratif:</b> %{customdata[4]}<br>"
                "<b>Kolaborator utama:</b> %{customdata[5]}<br>"
                "<b>Task dominan:</b> %{customdata[6]}<extra></extra>"
            ),
            showlegend=False,
        )
    )
    figure.update_layout(
        height=760,
        margin={"l": 20, "r": 20, "t": 20, "b": 100},
        paper_bgcolor=GRAPH_BG_COLOR,
        plot_bgcolor=GRAPH_BG_COLOR,
        font={"color": LIGHT_FONT_COLOR},
        xaxis={"showgrid": False, "zeroline": False, "showticklabels": False, "visible": False},
        yaxis={"showgrid": False, "zeroline": False, "showticklabels": False, "visible": False},
        hovermode="closest",
        hoverlabel={"bgcolor": "#111111", "font": {"color": LIGHT_FONT_COLOR}, "bordercolor": "#444444", "align": "left"},
    )
    return figure
