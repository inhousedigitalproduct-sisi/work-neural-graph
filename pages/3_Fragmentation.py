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
    timeline = (
        task_data.groupby("work_date", as_index=False)
        .agg(hours=("hours", "sum"))
        .sort_values("work_date")
    )
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
        xaxis={
            "title": {"font": {"color": "#FFFFFF"}},
            "tickfont": {"color": "#FFFFFF"},
            "gridcolor": "rgba(255,255,255,0.12)",
            "linecolor": "rgba(255,255,255,0.35)",
        },
        yaxis={
            "title": {"font": {"color": "#FFFFFF"}},
            "tickfont": {"color": "#FFFFFF"},
            "gridcolor": "rgba(255,255,255,0.18)",
            "linecolor": "rgba(255,255,255,0.35)",
        },
    )
    return figure


st.title("Fragmentation Analysis")
st.caption("Mendeteksi task yang pengerjaannya terputus, lalu memberi prioritas tindak lanjut berdasarkan filter aktif.")

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

with st.expander("Bagaimana pola pengerjaan task yang ideal?", expanded=True):
    st.markdown(
        """
**Pola ideal bukan berarti semua task harus selesai tanpa jeda.** Yang dicari adalah pola yang mudah ditelusuri dan alasan jedanya dapat dijelaskan.

- Task yang sama idealnya dikerjakan dalam **blok hari yang berdekatan** ketika memang sedang menjadi prioritas.
- Jika task harus berhenti, Note sebaiknya menjelaskan **blocker, dependency, keputusan yang ditunggu, atau next step**.
- Task yang berlangsung lama sebaiknya dipecah menjadi **subtask atau milestone** agar progres tidak terlihat sebagai satu pekerjaan yang sporadis.
- Pekerjaan support, rutin, atau menunggu pihak lain memang dapat memiliki fragmentasi tinggi. Karena itu skor adalah **sinyal untuk diskusi**, bukan penilaian kualitas kerja.

**Contoh sederhana:** Task A dikerjakan 1–3 Agustus lalu selesai. Polanya relatif kontinu. Task B muncul 1, 8, 17, dan 29 Agustus tanpa konteks jeda. Task B lebih layak ditelusuri: apakah karena dependency, perubahan prioritas, karakter support, atau task terlalu besar.
"""
    )

with st.expander("Cara membaca metrik fragmentasi", expanded=False):
    st.markdown(
        """
- **Fragmentation Score = Continuations + Interruption Days.** Makin tinggi, makin panjang/renggang pola pengerjaan task.
- **Interruption Days** adalah total hari kosong di antara dua tanggal pengerjaan task yang sama.
- **Continuity Ratio** adalah hari aktif dibagi rentang kalender task. Makin mendekati 100%, makin rapat pola pengerjaannya.
- **Max Gap** adalah jarak tanggal terpanjang antara dua kemunculan task berturut-turut.
- **Interruptions** menghitung berapa kali terdapat gap lebih dari satu hari.

Gunakan metrik secara bersama-sama. Skor tinggi pada pekerjaan support rutin dapat memiliki makna berbeda dari skor tinggi pada satu deliverable proyek yang seharusnya memiliki milestone jelas.
"""
    )

fragmented = snapshot.fragmentation[snapshot.fragmentation["interruption_count"] > 0]
top_fragmented = snapshot.fragmentation.head(3)
lowest_continuity = fragmented.sort_values("continuous_work_ratio").head(3)
max_gap = snapshot.fragmentation.sort_values("max_date_gap_days", ascending=False).head(1)

st.subheader("Ringkasan analisis")
filter_scope = f"{len(snapshot.filtered_dataframe)} entri, {snapshot.kpi.unique_tasks} task, dan {snapshot.kpi.active_days} hari aktif"
if fragmented.empty:
    st.success(f"Pada cakupan filter saat ini ({filter_scope}), tidak ada task yang memiliki jeda antarhari pengerjaan.")
else:
    st.warning(
        f"Pada cakupan filter saat ini ({filter_scope}), terdapat **{len(fragmented)} task** yang memiliki jeda pengerjaan. "
        "Gunakan daftar ini sebagai prioritas validasi konteks, bukan sebagai penilaian performa."
    )
    summary_left, summary_right = st.columns(2)
    with summary_left:
        st.markdown("**Task dengan sinyal fragmentasi tertinggi**")
        st.dataframe(
            top_fragmented[["task", "fragmentation_score", "total_interruption_days", "total_hours"]]
            .rename(columns={"task": "Task", "fragmentation_score": "Skor", "total_interruption_days": "Hari jeda", "total_hours": "Jam"}),
            hide_index=True,
            use_container_width=True,
        )
    with summary_right:
        gap_row = max_gap.iloc[0]
        st.markdown("**Temuan utama**")
        st.write(f"Jeda terpanjang adalah **{int(gap_row['max_date_gap_days'])} hari** pada task **{gap_row['task']}**.")
        if not lowest_continuity.empty:
            st.write(
                f"Kontinuitas terendah pada task yang terputus adalah **{lowest_continuity.iloc[0]['task']}** "
                f"({lowest_continuity.iloc[0]['continuous_work_ratio']:.0%})."
            )

st.subheader("Rekomendasi tindak lanjut")
if fragmented.empty:
    st.write(
        "Secara umum tidak ada sinyal jeda dominan pada filter aktif. Pertahankan konsistensi penamaan task dan dokumentasikan "
        "blocker/next step agar pola tetap mudah ditelusuri ketika cakupan pekerjaan bertambah."
    )
else:
    leading = top_fragmented.iloc[0]
    st.markdown("**Arah tindak lanjut manajerial**")
    st.write(
        f"Prioritaskan validasi pada kelompok task dengan fragmentasi tinggi, dimulai dari **{leading['task']}**. "
        "Tujuannya bukan mencari kesalahan, tetapi memastikan apakah pola jeda berasal dari dependency yang wajar, perubahan prioritas, "
        "karakter pekerjaan support, atau struktur task yang terlalu besar."
    )
    st.markdown("**Poin yang perlu didiskusikan manajemen**")
    management_points = [
        "Apakah task dengan jeda panjang memang menunggu dependency/approval eksternal, atau prioritasnya sering berubah?",
        "Apakah pekerjaan support/rutin sudah dipisahkan dari deliverable proyek sehingga pola keduanya tidak tercampur?",
        "Apakah task yang berlangsung lama perlu dipecah menjadi milestone/subtask dengan outcome dan next step yang lebih jelas?",
    ]
    for item in management_points:
        st.write(f"- {item}")

st.subheader("Fragmentation Table")
with st.expander("Help — cara membaca Fragmentation Table", expanded=False):
    st.markdown(
        """
Baca tabel dari kiri ke kanan untuk memahami **cakupan → rentang waktu → pola jeda → skor**:

- **Task / Project / Employees**: konteks pekerjaan yang dianalisis.
- **Total Hours**: total jam tercatat untuk task pada filter aktif.
- **Active Days**: jumlah tanggal task benar-benar dikerjakan.
- **Calendar Span**: rentang hari dari kemunculan pertama sampai terakhir, termasuk hari tanpa aktivitas.
- **Continuations**: jumlah perpindahan dari satu hari aktif ke hari aktif berikutnya (`Active Days - 1`).
- **Interruptions**: berapa kali terdapat gap lebih dari satu hari.
- **Max Gap**: gap tanggal terpanjang antar kemunculan task.
- **Interruption Days**: total hari kosong yang berada di antara hari-hari aktif.
- **Continuity Ratio**: `Active Days / Calendar Span`; makin tinggi berarti pola makin rapat.
- **Fragmentation Score**: `Continuations + Interruption Days`; gunakan untuk memprioritaskan review, bukan untuk menilai individu.

**Contoh:** sebuah task aktif 4 hari dalam rentang 5 hari biasanya lebih kontinu daripada task aktif 4 hari dalam rentang 30 hari, meskipun jumlah hari aktifnya sama.
"""
    )

fragmentation_table = snapshot.fragmentation[
    [
        "task",
        "project",
        "employees",
        "total_hours",
        "active_days",
        "calendar_span_days",
        "continuation_count",
        "interruption_count",
        "max_date_gap_days",
        "total_interruption_days",
        "continuous_work_ratio",
        "fragmentation_score",
    ]
].copy()
fragmentation_table.columns = [
    "Task",
    "Project",
    "Employees",
    "Total Hours",
    "Active Days",
    "Calendar Span",
    "Continuations",
    "Interruptions",
    "Max Gap",
    "Interruption Days",
    "Continuity Ratio",
    "Fragmentation Score",
]
st.dataframe(fragmentation_table, use_container_width=True, hide_index=True)

task_options = snapshot.fragmentation["task_key"].tolist()
selected_task_key = st.selectbox(
    "Selected Task Detail",
    task_options,
    key="fragmentation_selected_task_key",
    format_func=lambda value: snapshot.fragmentation.loc[
        snapshot.fragmentation["task_key"] == value, "task"
    ].iloc[0],
)

selected_task = snapshot.fragmentation[snapshot.fragmentation["task_key"] == selected_task_key].iloc[0]
detail_col1, detail_col2 = st.columns(2)
detail_col1.write(
    {
        "Task": selected_task["task"],
        "Project": selected_task["project"],
        "Employees": ", ".join(selected_task["employees"]),
        "Fragmentation Score": int(selected_task["fragmentation_score"]),
        "Band": selected_task["fragmentation_band"],
    }
)
detail_col2.write(
    {
        "First Work Date": selected_task["first_work_date"],
        "Last Work Date": selected_task["last_work_date"],
        "Active Days": int(selected_task["active_days"]),
        "Interruption Days": int(selected_task["total_interruption_days"]),
        "Continuity Ratio": round(float(selected_task["continuous_work_ratio"]), 4),
    }
)

st.subheader("Task Timeline")
st.caption("Batang menunjukkan jam yang tercatat pada setiap tanggal task dikerjakan. Ruang kosong antarbatang membantu melihat jeda pengerjaan.")
st.plotly_chart(build_task_timeline(snapshot.filtered_dataframe, selected_task_key), use_container_width=True)

with st.expander("Context Switching (detail teknis)", expanded=False):
    st.caption("Detail teknis ini menunjukkan perpindahan task dalam satu hari. Gunakan hanya bila diperlukan untuk investigasi lanjutan.")
    context_daily = snapshot.context_switch_daily.copy()
    if not context_daily.empty:
        context_daily["work_date"] = pd.to_datetime(context_daily["work_date"]).dt.date.astype(str)
    st.dataframe(context_daily, use_container_width=True)

with st.expander("Concurrency (detail teknis)", expanded=False):
    overall = snapshot.concurrency["date_overall"].copy()
    if not overall.empty:
        overall["work_date"] = pd.to_datetime(overall["work_date"]).dt.date.astype(str)
    st.dataframe(overall, use_container_width=True)
