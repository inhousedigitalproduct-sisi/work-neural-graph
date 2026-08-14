from __future__ import annotations

from collections.abc import Sequence

import networkx as nx
import pandas as pd
import plotly.graph_objects as go

EDGE_COLOR = "rgba(255,255,255,0.75)"
HOVER_BG_COLOR = "#111111"
HOVER_BORDER_COLOR = "#444444"
LIGHT_FONT_COLOR = "#FFFFFF"
NODE_BORDER_COLOR = "rgba(255,255,255,0.65)"
GRAPH_BG_COLOR = "#000000"


def scale_metric(values: Sequence[float], min_size: float, max_size: float) -> list[float]:
    if not values:
        return []
    unique_values = [float(value) for value in values]
    minimum = min(unique_values)
    maximum = max(unique_values)
    if minimum == maximum:
        midpoint = (min_size + max_size) / 2
        return [midpoint for _ in unique_values]
    return [
        min_size + ((value - minimum) / (maximum - minimum)) * (max_size - min_size)
        for value in unique_values
    ]


def _format_date(value: object) -> str:
    timestamp = pd.to_datetime(value)
    return timestamp.strftime("%d %b %Y")


def _truncate(value: object, limit: int = 100) -> str:
    if value is None or pd.isna(value):
        return "-"
    text = " ".join(str(value).split())
    if not text:
        return "-"
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "..."


def _build_node_activity_lookup(activity_dataframe: pd.DataFrame | None) -> dict[str, str]:
    """Create concise, human-readable activity details for node hover text."""
    if activity_dataframe is None or activity_dataframe.empty or "work_date" not in activity_dataframe.columns:
        return {}

    prepared = activity_dataframe.copy()
    prepared["work_date"] = pd.to_datetime(prepared["work_date"])
    prepared["hours"] = pd.to_numeric(prepared.get("hours"), errors="coerce").fillna(0.0)
    lookup: dict[str, str] = {}

    for work_date, group in prepared.groupby("work_date", sort=True):
        rows: list[str] = []
        for record in group.sort_values(["hours", "task"], ascending=[False, True]).head(6).to_dict("records"):
            task = _truncate(record.get("task"), 70)
            employee = _truncate(record.get("employee"), 45)
            project = _truncate(record.get("project"), 45)
            note = _truncate(record.get("note"), 100)
            hours = float(record.get("hours") or 0.0)
            rows.append(f"• {task} | {employee} | {project} | {hours:.2f} jam | Note: {note}")
        remaining = max(len(group) - len(rows), 0)
        if remaining:
            rows.append(f"• +{remaining} entri aktivitas lain")
        lookup[pd.to_datetime(work_date).date().isoformat()] = "<br>".join(rows) or "-"
    return lookup


def _build_related_date_lookup(edge_dataframe: pd.DataFrame) -> dict[str, str]:
    if edge_dataframe.empty:
        return {}
    related: dict[str, list[tuple[pd.Timestamp, str]]] = {}
    for edge in edge_dataframe.to_dict(orient="records"):
        source_timestamp = pd.to_datetime(edge["source"])
        target_timestamp = pd.to_datetime(edge["target"])
        source_key = source_timestamp.date().isoformat()
        target_key = target_timestamp.date().isoformat()
        shared_tasks = ", ".join(edge.get("shared_tasks", [])[:3]) or "task terkait"
        related.setdefault(source_key, []).append((target_timestamp, shared_tasks))
        related.setdefault(target_key, []).append((source_timestamp, shared_tasks))

    lookup: dict[str, str] = {}
    for key, values in related.items():
        sorted_values = sorted(values, key=lambda item: item[0])
        lookup[key] = "<br>".join(
            f"• {_format_date(timestamp)} — {tasks}" for timestamp, tasks in sorted_values
        )
    return lookup


def build_graph_figure(
    graph: nx.Graph,
    node_dataframe: pd.DataFrame,
    edge_dataframe: pd.DataFrame,
    node_size_metric: str = "total_hours",
    edge_width_metric: str = "task_count",
    show_node_labels: bool = True,
    activity_dataframe: pd.DataFrame | None = None,
) -> go.Figure:
    figure = go.Figure()
    if graph.number_of_nodes() == 0:
        figure.update_layout(
            title="No graph data available",
            paper_bgcolor=GRAPH_BG_COLOR,
            plot_bgcolor=GRAPH_BG_COLOR,
            font={"color": LIGHT_FONT_COLOR},
            xaxis={"showgrid": False, "zeroline": False, "showticklabels": False, "visible": False},
            yaxis={"showgrid": False, "zeroline": False, "showticklabels": False, "visible": False},
        )
        return figure

    positions = nx.spring_layout(graph, seed=42, k=None)
    edge_widths = scale_metric(edge_dataframe[edge_width_metric].tolist(), 1.5, 8.0) if not edge_dataframe.empty else []
    for edge_index, edge in enumerate(edge_dataframe.to_dict(orient="records")):
        source = edge["source"].date().isoformat()
        target = edge["target"].date().isoformat()
        x0, y0 = positions[source]
        x1, y1 = positions[target]
        figure.add_trace(
            go.Scatter(
                x=[x0, x1],
                y=[y0, y1],
                mode="lines",
                line={"width": edge_widths[edge_index], "color": EDGE_COLOR},
                hoverinfo="skip",
                showlegend=False,
            )
        )
        figure.add_trace(
            go.Scatter(
                x=[(x0 + x1) / 2],
                y=[(y0 + y1) / 2],
                mode="markers",
                marker={"size": max(edge_widths[edge_index] + 4, 8), "color": "rgba(0,0,0,0)"},
                customdata=[
                    [
                        _format_date(source),
                        _format_date(target),
                        edge["gap_days"],
                        edge["task_count"],
                        ", ".join(edge["shared_tasks"][:5]),
                        ", ".join(edge["employees"][:5]),
                        ", ".join(edge["projects"][:5]),
                        round(float(edge["related_hours"]), 2),
                    ]
                ],
                hovertemplate=(
                    "<b>Relasi tanggal</b><br>"
                    "%{customdata[0]} → %{customdata[1]}<br>"
                    "<b>Alasan relasi:</b> task yang sama muncul pada kedua tanggal<br>"
                    "<b>Jarak tanggal:</b> %{customdata[2]} hari<br>"
                    "<b>Jumlah task terkait:</b> %{customdata[3]}<br>"
                    "<b>Task:</b> %{customdata[4]}<br>"
                    "<b>Pegawai:</b> %{customdata[5]}<br>"
                    "<b>Proyek:</b> %{customdata[6]}<br>"
                    "<b>Total jam terkait:</b> %{customdata[7]}<extra></extra>"
                ),
                showlegend=False,
            )
        )

    node_sizes = scale_metric(node_dataframe[node_size_metric].tolist(), 18, 48)
    metric_labels = {
        "total_hours": "Total jam kerja",
        "unique_tasks": "Jumlah task",
        "unique_employees": "Jumlah pegawai",
        "unique_projects": "Jumlah proyek",
        "degree": "Jumlah relasi tanggal",
    }
    metric_label = metric_labels.get(node_size_metric, node_size_metric.replace("_", " ").title())
    activity_lookup = _build_node_activity_lookup(activity_dataframe)
    related_date_lookup = _build_related_date_lookup(edge_dataframe)

    node_x: list[float] = []
    node_y: list[float] = []
    node_text: list[str] = []
    customdata: list[list[object]] = []
    for node in node_dataframe.to_dict(orient="records"):
        node_name = node["date"].date().isoformat()
        x, y = positions[node_name]
        node_x.append(x)
        node_y.append(y)
        node_text.append(_format_date(node_name))
        customdata.append(
            [
                _format_date(node_name),
                round(float(node["total_hours"]), 2),
                int(node["unique_tasks"]),
                int(node["unique_employees"]),
                int(node["unique_projects"]),
                int(node["degree"]),
                ", ".join(node.get("employees", [])) or "-",
                related_date_lookup.get(node_name, "Tidak ada"),
                activity_lookup.get(node_name, "Detail aktivitas tidak tersedia"),
            ]
        )

    figure.add_trace(
        go.Scatter(
            x=node_x,
            y=node_y,
            mode="markers+text" if show_node_labels else "markers",
            text=node_text if show_node_labels else None,
            textposition="top center",
            textfont={"color": LIGHT_FONT_COLOR},
            marker={
                "size": node_sizes,
                "color": node_dataframe[node_size_metric].tolist(),
                "colorscale": "YlGnBu",
                "line": {"width": 1, "color": NODE_BORDER_COLOR},
                "showscale": True,
                "colorbar": {
                    # A horizontal legend avoids looking like a Y axis. Node position is
                    # determined exclusively by the network layout, not by this metric.
                    "orientation": "h",
                    "x": 0.5,
                    "xanchor": "center",
                    "y": -0.13,
                    "yanchor": "top",
                    "len": 0.52,
                    "thickness": 14,
                    "title": {
                        "text": f"Warna node — {metric_label}",
                        "side": "top",
                        "font": {"color": LIGHT_FONT_COLOR},
                    },
                    "tickfont": {"color": LIGHT_FONT_COLOR},
                    "bgcolor": "rgba(0,0,0,0)",
                    "outlinecolor": NODE_BORDER_COLOR,
                },
            },
            customdata=customdata,
            hovertemplate=(
                "<b>Tanggal:</b> %{customdata[0]}<br>"
                "<b>Total jam:</b> %{customdata[1]}<br>"
                "<b>Task aktif:</b> %{customdata[2]}<br>"
                "<b>Jumlah pegawai:</b> %{customdata[3]}<br>"
                "<b>Jumlah proyek:</b> %{customdata[4]}<br>"
                "<b>Relasi tanggal:</b> %{customdata[5]}<br>"
                "<b>Pegawai aktif:</b> %{customdata[6]}<br>"
                "<b>Terhubung ke:</b> %{customdata[7]}<br><br>"
                "<b>Detail aktivitas (maks. 6 entri):</b><br>%{customdata[8]}<extra></extra>"
            ),
            showlegend=False,
        )
    )

    figure.update_layout(
        margin={"l": 20, "r": 20, "t": 20, "b": 105},
        paper_bgcolor=GRAPH_BG_COLOR,
        plot_bgcolor=GRAPH_BG_COLOR,
        font={"color": LIGHT_FONT_COLOR},
        xaxis={"showgrid": False, "zeroline": False, "showticklabels": False, "visible": False},
        yaxis={"showgrid": False, "zeroline": False, "showticklabels": False, "visible": False},
        hovermode="closest",
        hoverlabel={
            "bgcolor": HOVER_BG_COLOR,
            "font": {"color": LIGHT_FONT_COLOR},
            "bordercolor": HOVER_BORDER_COLOR,
            "align": "left",
        },
        height=760,
    )
    return figure
