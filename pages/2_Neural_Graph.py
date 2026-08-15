from __future__ import annotations

import pandas as pd
import streamlit as st

from src.analytics.service import AnalyticsService
from src.graph.builder import apply_graph_filters
from src.graph.collaboration import build_collaboration_graph
from src.graph.collaboration_visualizer import build_collaboration_figure
from src.services import TimesheetDataService
from src.ui.components import render_analytics_summary, render_shared_filters
from src.utils.config import get_config

config = get_config()
dataset_service = TimesheetDataService(config.db_path)
analytics_service = AnalyticsService(config.db_path)

st.title("Neural Graph — Kolaborasi")
st.caption("Peta kolaborasi antar-karyawan berdasarkan task yang sama pada periode dan filter aktif. Tanggal tidak digunakan sebagai pembentuk relasi.")

source_dataframe = dataset_service.load_active_dataset()
if source_dataframe.empty:
    st.info("Belum ada data timesheet. Muat data dari halaman Load Data.")
    st.stop()

source_dataframe["work_date"] = pd.to_datetime(source_dataframe["work_date"])
filters, _ = render_shared_filters(source_dataframe)
filtered = apply_graph_filters(source_dataframe, filters)
result = build_collaboration_graph(filtered)
snapshot = analytics_service.build_snapshot(filters=filters)

if result.filtered_dataframe.empty:
    st.info("Filter saat ini tidak menghasilkan data.")
    st.stop()

summary = result.summary
a, b, c = st.columns(3)
a.metric("Karyawan", summary.employees)
b.metric("Relasi kolaborasi", summary.collaboration_links)
c.metric("Task kolaboratif", summary.collaborative_tasks)
d, e, f = st.columns(3)
d.metric("Project kolaboratif", summary.projects)
e.metric("Jam pada task kolaboratif", f"{summary.collaborative_hours:.2f}")
f.metric("Rata-rata kolaborator", f"{summary.average_collaborators:.2f}")

with st.expander("Cara membaca Collaboration Graph", expanded=True):
    st.markdown(
        """
- **Node/dot = karyawan.**
- **Garis = dua karyawan pernah mengerjakan `task_key` yang sama** dalam periode/filter aktif, walaupun tanggal pengerjaannya berbeda.
- **Dot lebih besar = nilai metrik node lebih tinggi.** Default-nya jumlah kolaborator unik.
- **Garis lebih tebal = hubungan lebih kuat.** Default-nya jumlah task bersama.
- Arahkan kursor ke **dot** untuk melihat jumlah kolaborator, task/project kolaboratif, jam, kolaborator utama, dan task dominan.
- Arahkan kursor ke **titik tengah garis** untuk melihat task/project yang menjadi dasar hubungan dua karyawan.
"""
    )

with st.sidebar:
    st.divider()
    st.subheader("Collaboration Graph")
    node_size_metric = st.selectbox(
        "Ukuran node",
        ["collaborator_count", "collaborative_task_count", "collaborative_hours", "project_count"],
        format_func=lambda value: {
            "collaborator_count": "Jumlah kolaborator",
            "collaborative_task_count": "Task kolaboratif",
            "collaborative_hours": "Jam kolaboratif",
            "project_count": "Project kolaboratif",
        }[value],
        key="neural_graph_node_size_metric",
    )
    edge_width_metric = st.selectbox(
        "Ketebalan garis",
        ["shared_task_count", "related_hours"],
        format_func=lambda value: "Jumlah task bersama" if value == "shared_task_count" else "Total jam terkait",
        key="neural_graph_edge_width_metric",
    )
    show_labels = st.toggle("Tampilkan nama karyawan", value=summary.employees <= 40, key="neural_graph_show_labels")
    min_shared_tasks = 1
    if not result.edge_dataframe.empty:
        maximum = int(result.edge_dataframe["shared_task_count"].max())
        if maximum > 1:
            min_shared_tasks = st.slider(
                "Minimum task bersama",
                min_value=1,
                max_value=maximum,
                value=1,
                key="neural_graph_min_shared_tasks",
            )
        else:
            st.caption("Minimum task bersama: 1 (semua relasi hanya memiliki 1 task bersama)")

edges = result.edge_dataframe
if not edges.empty:
    edges = edges[edges["shared_task_count"] >= min_shared_tasks].reset_index(drop=True)

display_graph = result.graph.copy()
for source, target in list(display_graph.edges):
    if edges.empty or not (((edges["source"] == source) & (edges["target"] == target)) | ((edges["source"] == target) & (edges["target"] == source))).any():
        display_graph.remove_edge(source, target)

if result.summary.collaboration_links == 0:
    st.info("Tidak ada task yang dikerjakan oleh lebih dari satu karyawan pada filter aktif. Semua karyawan ditampilkan sebagai node tanpa garis.")

figure = build_collaboration_figure(
    display_graph,
    result.node_dataframe,
    edges,
    node_size_metric=node_size_metric,
    edge_width_metric=edge_width_metric,
    show_node_labels=show_labels,
)
st.subheader("Peta kolaborasi karyawan")
st.plotly_chart(figure, use_container_width=True)

st.subheader("Period Analysis")
render_analytics_summary(
    total_hours=snapshot.kpi.total_hours,
    active_days=snapshot.kpi.active_days,
    unique_tasks=snapshot.kpi.unique_tasks,
    unique_employees=snapshot.kpi.unique_employees,
    unique_projects=snapshot.kpi.unique_projects,
    fragmented_tasks=snapshot.kpi.fragmented_tasks,
    interrupted_tasks=snapshot.kpi.interrupted_tasks,
    average_context_switches=snapshot.kpi.average_context_switches,
    average_continuity_ratio=snapshot.kpi.average_continuity_ratio,
)

with st.expander("Relasi kolaborasi", expanded=False):
    table = edges.copy()
    if not table.empty:
        table["shared_tasks"] = table["shared_tasks"].map(lambda values: ", ".join(values))
        table["projects"] = table["projects"].map(lambda values: ", ".join(values))
    st.dataframe(table, use_container_width=True, hide_index=True)

with st.expander("Detail karyawan", expanded=False):
    table = result.node_dataframe.copy()
    if not table.empty:
        for column in ["collaborators", "top_collaborators", "top_tasks"]:
            table[column] = table[column].map(lambda values: ", ".join(values))
    st.dataframe(table, use_container_width=True, hide_index=True)
