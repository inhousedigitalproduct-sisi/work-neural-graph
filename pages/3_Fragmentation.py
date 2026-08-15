from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.analytics.service import AnalyticsService
from src.services import TimesheetDataService
from src.ui.components import render_analytics_summary, render_shared_filters
from src.utils.config import get_config

config = get_config()
service = AnalyticsService(config.db_path)
dataset_service = TimesheetDataService(config.db_path)


def build_task_timeline(dataframe: pd.DataFrame, task_key: str) -> go.Figure:
    task_data = dataframe[dataframe["task_key"] == task_key].copy()
    task_data["work_date"] = pd.to_datetime(task_data["work_date"])
    timeline = task_data.groupby("work_date", as_index=False).agg(hours=("hours", "sum")).sort_values("work_date")
    figure = go.Figure(
        data=[
            go.Bar(
                x=timeline["work_date"].tolist(),
                y=timeline["hours"].tolist(),
                marker_color="#FFFFFF",
                hovertemplate="Tanggal: %{x|%d %b %Y}<br>Jam: %{y:.2f}<extra></extra>",
            )
        ]
    )
    figure.update_layout(
        height=320,
        margin={"l": 20, "r": 20, "t": 20, "b": 20},
        xaxis_title="Tanggal kerja",
        yaxis_title="Jam",
        paper_bgcolor="#000000",
        plot_bgcolor="#000000",
        font={"color": "#FFFFFF"},
        hoverlabel={"bgcolor": "#111111", "font": {"color": "#FFFFFF"}, "bordercolor": "#444444"},
        xaxis={"gridcolor": "rgba(255,255,255,0.12)", "linecolor": "rgba(255,255,255,0.35)"},
        yaxis={"gridcolor": "rgba(255,255,255,0.18)", "linecolor": "rgba(255,255,255,0.35)"},
    )
    return figure


st.title("Fragmentation Analysis")
st.caption("Mendeteksi pola task yang terputus berdasarkan data timesheet pada filter aktif.")

source_dataframe = dataset_service.load_active_dataset()
if source_dataframe.empty:
    st.info("No timesheet data is available. Load data from the Load Data page.")
    st.stop()

filters, _ = render_shared_filters(source_dataframe)
snapshot = service.build_snapshot(filters=filters)
if snapshot.filtered_dataframe.empty:
    st.info("The selected filters returned no rows.")
    st.stop()

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

with st.expander("Cara membaca metrik fragmentasi", expanded=True):
    st.markdown(
        """
- **Fragmentation Score = Continuations + Interruption Days.** Semakin tinggi, semakin renggang pola pengerjaan task.
- **Interruption Days** adalah total hari kosong di antara dua tanggal pengerjaan task yang sama.
- **Continuity Ratio** adalah hari aktif dibagi rentang kalender task.
- **Max Gap** adalah jarak tanggal terpanjang antara dua kemunculan task berturut-turut.
- Angka-angka ini adalah **sinyal pola kerja**, bukan rekomendasi otomatis dan bukan penilaian performa individu.
"""
    )

fragmented = snapshot.fragmentation[snapshot.fragmentation["interruption_count"] > 0]
st.subheader("Ringkasan analisis")
if fragmented.empty:
    st.success("Tidak ada task yang memiliki jeda antarhari pengerjaan pada filter aktif.")
else:
    st.info(
        f"Terdapat {len(fragmented)} task dengan jeda pengerjaan pada filter aktif. "
        "Gunakan tabel dan timeline untuk membaca pola aktual tanpa rekomendasi otomatis."
    )

st.subheader("Fragmentation Table")
columns = [
    "task", "project", "employees", "total_hours", "active_days", "calendar_span_days",
    "continuation_count", "interruption_count", "max_date_gap_days", "total_interruption_days",
    "continuous_work_ratio", "fragmentation_score",
]
fragmentation_table = snapshot.fragmentation[columns].copy()
fragmentation_table.columns = [
    "Task", "Project", "Employees", "Total Hours", "Active Days", "Calendar Span",
    "Continuations", "Interruptions", "Max Gap", "Interruption Days", "Continuity Ratio", "Fragmentation Score",
]
st.dataframe(fragmentation_table, use_container_width=True, hide_index=True)

if snapshot.fragmentation.empty:
    st.stop()

task_options = snapshot.fragmentation["task_key"].tolist()
selected_task_key = st.selectbox(
    "Selected Task Detail",
    task_options,
    key="fragmentation_selected_task_key",
    format_func=lambda value: snapshot.fragmentation.loc[snapshot.fragmentation["task_key"] == value, "task"].iloc[0],
)
selected_task = snapshot.fragmentation[snapshot.fragmentation["task_key"] == selected_task_key].iloc[0]
left, right = st.columns(2)
left.write({
    "Task": selected_task["task"],
    "Project": selected_task["project"],
    "Employees": ", ".join(selected_task["employees"]),
    "Fragmentation Score": int(selected_task["fragmentation_score"]),
    "Band": selected_task["fragmentation_band"],
})
right.write({
    "First Work Date": selected_task["first_work_date"],
    "Last Work Date": selected_task["last_work_date"],
    "Active Days": int(selected_task["active_days"]),
    "Interruption Days": int(selected_task["total_interruption_days"]),
    "Continuity Ratio": round(float(selected_task["continuous_work_ratio"]), 4),
})

st.subheader("Task Timeline")
st.caption("Batang menunjukkan jam pada setiap tanggal task dikerjakan; ruang kosong antarbatang menunjukkan jeda.")
st.plotly_chart(build_task_timeline(snapshot.filtered_dataframe, selected_task_key), use_container_width=True)

with st.expander("Context Switching", expanded=False):
    st.dataframe(snapshot.context_switch_summary, use_container_width=True, hide_index=True)

with st.expander("Continuity", expanded=False):
    st.dataframe(snapshot.continuity, use_container_width=True, hide_index=True)
