from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.analytics.service import AnalyticsService
from src.services import TimesheetDataService
from src.ui.components import render_shared_filters
from src.utils.config import get_config

config = get_config()
service = AnalyticsService(config.db_path)
dataset_service = TimesheetDataService(config.db_path)


def continuity_pattern(value: float) -> str:
    ratio = float(value)
    if ratio >= 0.75:
        return "Kontinu"
    if ratio >= 0.50:
        return "Cukup kontinu"
    if ratio >= 0.25:
        return "Terputus"
    return "Sangat terputus"


def switching_pattern(value: float) -> str:
    switches = float(value)
    if switches < 1:
        return "Fokus"
    if switches < 3:
        return "Cukup tersebar"
    return "Sangat tersebar"


def build_task_timeline(dataframe: pd.DataFrame, task_key: str) -> go.Figure:
    task_data = dataframe[dataframe["task_key"] == task_key].copy()
    task_data["work_date"] = pd.to_datetime(task_data["work_date"])
    timeline = task_data.groupby("work_date", as_index=False).agg(hours=("hours", "sum")).sort_values("work_date")
    figure = go.Figure(
        data=[go.Bar(
            x=timeline["work_date"].tolist(),
            y=timeline["hours"].tolist(),
            hovertemplate="Tanggal: %{x|%d %b %Y}<br>Jam: %{y:.2f}<extra></extra>",
        )]
    )
    figure.update_layout(
        height=320,
        margin={"l": 20, "r": 20, "t": 20, "b": 20},
        xaxis_title="Tanggal kerja",
        yaxis_title="Jam",
        hovermode="closest",
    )
    return figure


def build_context_switch_bar(summary: pd.DataFrame) -> go.Figure:
    view = summary.sort_values("average_context_switches_per_active_day", ascending=True)
    figure = go.Figure(go.Bar(
        x=view["average_context_switches_per_active_day"],
        y=view["employee"],
        orientation="h",
        customdata=view[["active_days", "max_context_switches_single_day"]],
        hovertemplate=(
            "<b>%{y}</b><br>Rata-rata pindah task/hari: %{x:.2f}<br>"
            "Hari aktif: %{customdata[0]}<br>Maksimum dalam sehari: %{customdata[1]}<extra></extra>"
        ),
    ))
    figure.update_layout(
        height=max(360, 34 * len(view)),
        margin={"l": 20, "r": 20, "t": 20, "b": 20},
        xaxis_title="Rata-rata perpindahan task per hari aktif",
        yaxis_title="",
    )
    return figure


def build_context_switch_daily(daily: pd.DataFrame, employee: str) -> go.Figure:
    view = daily[daily["employee"] == employee].copy().sort_values("work_date")
    figure = go.Figure(go.Scatter(
        x=view["work_date"],
        y=view["context_switches"],
        mode="lines+markers",
        customdata=view[["unique_tasks", "unique_projects", "total_hours"]],
        hovertemplate=(
            "Tanggal: %{x|%d %b %Y}<br>Perpindahan task: %{y}<br>"
            "Task unik: %{customdata[0]}<br>Project unik: %{customdata[1]}<br>"
            "Total jam: %{customdata[2]:.2f}<extra></extra>"
        ),
    ))
    figure.update_layout(
        height=320,
        margin={"l": 20, "r": 20, "t": 20, "b": 20},
        xaxis_title="Tanggal",
        yaxis_title="Perpindahan task",
    )
    return figure


def build_continuity_scatter(continuity: pd.DataFrame) -> go.Figure:
    view = continuity.copy()
    view["continuity_percent"] = view["continuous_work_ratio"].astype(float) * 100
    figure = go.Figure(go.Scatter(
        x=view["calendar_span_days"],
        y=view["continuity_percent"],
        mode="markers",
        text=view["task"],
        customdata=view[["project", "active_days", "max_date_gap_days"]],
        hovertemplate=(
            "<b>%{text}</b><br>Project: %{customdata[0]}<br>Rentang: %{x} hari<br>"
            "Hari dikerjakan: %{customdata[1]}<br>Jeda terpanjang: %{customdata[2]} hari<br>"
            "Kontinuitas: %{y:.0f}%<extra></extra>"
        ),
    ))
    figure.update_layout(
        height=430,
        margin={"l": 20, "r": 20, "t": 20, "b": 20},
        xaxis_title="Rentang pengerjaan (hari)",
        yaxis_title="Tingkat kontinuitas (%)",
        yaxis={"range": [0, 105]},
    )
    return figure


def build_continuity_ranking(continuity: pd.DataFrame) -> go.Figure:
    view = continuity.copy()
    view["continuity_percent"] = view["continuous_work_ratio"].astype(float) * 100
    view = view.sort_values("continuity_percent", ascending=True).tail(25)
    figure = go.Figure(go.Bar(
        x=view["continuity_percent"],
        y=view["task"],
        orientation="h",
        customdata=view[["calendar_span_days", "max_date_gap_days"]],
        hovertemplate=(
            "<b>%{y}</b><br>Kontinuitas: %{x:.0f}%<br>Rentang: %{customdata[0]} hari<br>"
            "Jeda terpanjang: %{customdata[1]} hari<extra></extra>"
        ),
    ))
    figure.update_layout(
        height=max(360, 32 * len(view)),
        margin={"l": 20, "r": 20, "t": 20, "b": 20},
        xaxis_title="Tingkat kontinuitas (%)",
        yaxis_title="",
        xaxis={"range": [0, 105]},
    )
    return figure


st.title("Fragmentation Analysis")
st.caption("Membaca pola jeda, perpindahan task, dan kontinuitas kerja dengan visual yang lebih mudah dipahami.")

source_dataframe = dataset_service.load_active_dataset()
if source_dataframe.empty:
    st.info("Belum ada data timesheet. Muat data dari halaman Load Data.")
    st.stop()

filters, _ = render_shared_filters(source_dataframe)
snapshot = service.build_snapshot(filters=filters)
if snapshot.filtered_dataframe.empty:
    st.info("Filter saat ini tidak menghasilkan data.")
    st.stop()

fragmentation = snapshot.fragmentation.copy()
fragmented = fragmentation[fragmentation["interruption_count"] > 0].copy()
continuity = snapshot.continuity.copy()

scope_text = (
    f"Scope aktif: {len(snapshot.filtered_dataframe):,} entri • "
    f"{snapshot.kpi.unique_tasks} task • {snapshot.kpi.unique_employees} karyawan • "
    f"{snapshot.kpi.unique_projects} project"
)
st.caption(scope_text)

median_continuity = float(continuity["continuous_work_ratio"].median()) * 100 if not continuity.empty else 0.0
longest_gap = int(fragmentation["max_date_gap_days"].max()) if not fragmentation.empty else 0
fragmented_pct = (len(fragmented) / len(fragmentation) * 100) if len(fragmentation) else 0.0

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Task dianalisis", len(fragmentation))
k2.metric("Task dengan jeda", len(fragmented))
k3.metric("Task dengan jeda", f"{fragmented_pct:.0f}%", help="Persentase task yang memiliki jeda antarhari pengerjaan.")
k4.metric("Median kontinuitas", f"{median_continuity:.0f}%", help="Nilai tengah tingkat kontinuitas seluruh task pada scope aktif.")
k5.metric("Jeda terpanjang", f"{longest_gap} hari")

st.subheader("Ringkasan pola")
if fragmented.empty:
    st.success("Tidak ada task yang memiliki jeda antarhari pengerjaan pada filter aktif.")
else:
    low_continuity = int((continuity["continuous_work_ratio"] < 0.50).sum()) if not continuity.empty else 0
    st.info(
        f"{len(fragmented)} dari {len(fragmentation)} task memiliki jeda pengerjaan. "
        f"{low_continuity} task memiliki tingkat kontinuitas di bawah 50%. "
        "Gunakan tabel dan visual di bawah untuk melihat task yang paling renggang polanya."
    )

with st.expander("Cara membaca analisis ini", expanded=False):
    st.markdown(
        """
- **Hari Dikerjakan** = jumlah hari aktual task muncul di timesheet.
- **Rentang Pengerjaan** = jarak dari tanggal pertama sampai tanggal terakhir task.
- **Jeda Terpanjang** = jarak tanggal terpanjang antara dua kemunculan task berturut-turut.
- **Tingkat Kontinuitas** = Hari Dikerjakan / Rentang Pengerjaan. Semakin tinggi, semakin rapat pola pengerjaannya.
- Label pola adalah interpretasi keteraturan waktu, **bukan penilaian performa individu**.
"""
    )

st.subheader("Fragmentation Table")
fragmentation_table = fragmentation[[
    "task", "project", "employees", "active_days", "calendar_span_days",
    "max_date_gap_days", "continuous_work_ratio",
]].copy()
fragmentation_table["employees"] = fragmentation_table["employees"].map(lambda values: ", ".join(values))
fragmentation_table["continuous_work_ratio"] = fragmentation_table["continuous_work_ratio"].astype(float) * 100
fragmentation_table["Pola"] = fragmentation_table["continuous_work_ratio"].map(lambda value: continuity_pattern(value / 100))
fragmentation_table.columns = [
    "Task", "Project", "Karyawan", "Hari Dikerjakan", "Rentang Pengerjaan (hari)",
    "Jeda Terpanjang (hari)", "Tingkat Kontinuitas (%)", "Pola",
]
st.dataframe(
    fragmentation_table,
    use_container_width=True,
    hide_index=True,
    column_config={"Tingkat Kontinuitas (%)": st.column_config.NumberColumn(format="%.0f%%")},
)

if fragmentation.empty:
    st.stop()

task_options = fragmentation["task_key"].tolist()
selected_task_key = st.selectbox(
    "Pilih task untuk melihat detail",
    task_options,
    key="fragmentation_selected_task_key",
    format_func=lambda value: fragmentation.loc[fragmentation["task_key"] == value, "task"].iloc[0],
)
selected_task = fragmentation[fragmentation["task_key"] == selected_task_key].iloc[0]
selected_continuity = float(selected_task["continuous_work_ratio"])
selected_pattern = continuity_pattern(selected_continuity)

st.subheader(str(selected_task["task"]))
st.markdown(
    f"**{selected_pattern}.** Task dikerjakan pada **{int(selected_task['active_days'])} hari** "
    f"dalam rentang **{int(selected_task['calendar_span_days'])} hari**. "
    f"Jeda terpanjang **{int(selected_task['max_date_gap_days'])} hari**, "
    f"dengan tingkat kontinuitas **{selected_continuity * 100:.0f}%**."
)
st.caption(
    f"Project: {selected_task['project']} • Karyawan: {', '.join(selected_task['employees'])} • "
    f"Total jam: {float(selected_task['total_hours']):.2f}"
)

st.subheader("Task Timeline")
st.caption("Batang menunjukkan jam pada setiap tanggal task dikerjakan. Ruang kosong antarbatang menunjukkan jeda.")
st.plotly_chart(build_task_timeline(snapshot.filtered_dataframe, selected_task_key), use_container_width=True)

with st.expander("Detail perhitungan task", expanded=False):
    detail = pd.DataFrame([{
        "Continuations": int(selected_task["continuation_count"]),
        "Interruptions": int(selected_task["interruption_count"]),
        "Average Gap (hari)": round(float(selected_task["average_date_gap_days"]), 2),
        "Interruption Days": int(selected_task["total_interruption_days"]),
        "Fragmentation Score": int(selected_task["fragmentation_score"]),
        "Band": selected_task["fragmentation_band"],
        "Tanggal pertama": selected_task["first_work_date"],
        "Tanggal terakhir": selected_task["last_work_date"],
    }])
    st.dataframe(detail, use_container_width=True, hide_index=True)

st.divider()
st.subheader("Context Switching")
st.caption("Menunjukkan seberapa sering karyawan berpindah task dalam satu hari aktif. Nilai ini menggambarkan pola fokus, bukan produktivitas.")

context_summary = snapshot.context_switch_summary.copy()
context_daily = snapshot.context_switch_daily.copy()
if context_summary.empty:
    st.info("Belum ada data Context Switching pada scope aktif.")
else:
    st.plotly_chart(build_context_switch_bar(context_summary), use_container_width=True)
    human_context = context_summary.copy()
    human_context["Pola"] = human_context["average_context_switches_per_active_day"].map(switching_pattern)
    human_context = human_context.rename(columns={
        "employee": "Karyawan",
        "active_days": "Hari Aktif",
        "average_context_switches_per_active_day": "Rata-rata Pindah Task/Hari",
        "max_context_switches_single_day": "Pindah Task Tertinggi",
    })
    st.dataframe(
        human_context[["Karyawan", "Hari Aktif", "Rata-rata Pindah Task/Hari", "Pindah Task Tertinggi", "Pola"]],
        use_container_width=True,
        hide_index=True,
        column_config={"Rata-rata Pindah Task/Hari": st.column_config.NumberColumn(format="%.2f")},
    )

    employee = st.selectbox(
        "Lihat perpindahan task per hari",
        context_summary["employee"].tolist(),
        key="fragmentation_context_employee",
    )
    employee_row = context_summary[context_summary["employee"] == employee].iloc[0]
    avg_switch = float(employee_row["average_context_switches_per_active_day"])
    st.caption(
        f"{employee} memiliki pola **{switching_pattern(avg_switch).lower()}**: rata-rata "
        f"{avg_switch:.2f} perpindahan task per hari aktif, dengan maksimum "
        f"{int(employee_row['max_context_switches_single_day'])} dalam satu hari."
    )
    st.plotly_chart(build_context_switch_daily(context_daily, employee), use_container_width=True)

    with st.expander("Lihat detail perhitungan Context Switching", expanded=False):
        st.dataframe(context_daily, use_container_width=True, hide_index=True)

st.divider()
st.subheader("Continuity")
st.caption("Menunjukkan seberapa rapat sebuah task dikerjakan sepanjang rentang waktunya. Titik kanan-bawah berarti rentang panjang dengan kontinuitas rendah.")

if continuity.empty:
    st.info("Belum ada data Continuity pada scope aktif.")
else:
    st.plotly_chart(build_continuity_scatter(continuity), use_container_width=True)
    st.caption("Ranking di bawah membantu membandingkan tingkat kontinuitas antar-task. Maksimal 25 task ditampilkan agar tetap terbaca.")
    st.plotly_chart(build_continuity_ranking(continuity), use_container_width=True)

    human_continuity = continuity.copy()
    human_continuity["Tingkat Kontinuitas (%)"] = human_continuity["continuous_work_ratio"].astype(float) * 100
    human_continuity["Pola"] = human_continuity["continuous_work_ratio"].map(continuity_pattern)
    human_continuity = human_continuity.rename(columns={
        "task": "Task",
        "project": "Project",
        "active_days": "Hari Dikerjakan",
        "calendar_span_days": "Rentang Pengerjaan (hari)",
        "max_date_gap_days": "Jeda Terpanjang (hari)",
    })
    st.dataframe(
        human_continuity[[
            "Task", "Project", "Hari Dikerjakan", "Rentang Pengerjaan (hari)",
            "Jeda Terpanjang (hari)", "Tingkat Kontinuitas (%)", "Pola",
        ]],
        use_container_width=True,
        hide_index=True,
        column_config={"Tingkat Kontinuitas (%)": st.column_config.NumberColumn(format="%.0f%%")},
    )

    with st.expander("Lihat detail perhitungan Continuity", expanded=False):
        st.dataframe(snapshot.continuity, use_container_width=True, hide_index=True)
