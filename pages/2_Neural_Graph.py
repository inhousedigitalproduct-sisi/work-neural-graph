from __future__ import annotations

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from src.analytics.service import AnalyticsService
from src.graph.builder import GraphFilterConfig, apply_graph_filters
from src.graph.collaboration import build_collaboration_graph
from src.graph.collaboration_mentions import (
    build_acknowledgement_insights,
    build_mention_diagnostics,
    build_visible_directional_signals,
    extract_collaboration_mentions,
    load_employee_aliases,
)
from src.graph.pinball_animation import inject_pinball_effect
from src.graph.sigma_renderer import build_sigma_html
from src.services import TimesheetDataService
from src.ui.components import render_analytics_summary
from src.utils.config import get_config

config = get_config()
dataset_service = TimesheetDataService(config.db_path)
analytics_service = AnalyticsService(config.db_path)

st.title("Neural Graph — Kolaborasi")
st.caption(
    "Eksplorasi hubungan antar-karyawan berdasarkan task yang sama. "
    "Atur nama project dan periode untuk melihat bagaimana pola kolaborasi berubah pada scope yang berbeda."
)

source_dataframe = dataset_service.load_active_dataset()
if source_dataframe.empty:
    st.info("Belum ada data timesheet. Muat data dari halaman Load Data.")
    st.stop()

source_dataframe["work_date"] = pd.to_datetime(source_dataframe["work_date"], errors="coerce")
source_dataframe = source_dataframe[source_dataframe["work_date"].notna()].copy()
if source_dataframe.empty:
    st.info("Dataset tidak memiliki tanggal kerja valid untuk membangun Collaboration Graph.")
    st.stop()

min_date = source_dataframe["work_date"].min().date()
max_date = source_dataframe["work_date"].max().date()
projects = sorted(source_dataframe["project"].dropna().astype(str).unique().tolist())

with st.container(border=True):
    st.markdown("#### Scope Kolaborasi")
    st.caption("Nama Project dan rentang tanggal menjadi filter utama. Kosongkan Nama Project untuk melihat seluruh project.")
    date_col, project_col = st.columns([1.0, 1.8], gap="medium")
    with date_col:
        date_range = st.date_input(
            "Range Date",
            value=(min_date, max_date),
            min_value=min_date,
            max_value=max_date,
            key="neural_graph_date_range",
        )
    with project_col:
        selected_projects = st.multiselect(
            "Nama Project",
            projects,
            key="neural_graph_projects",
            placeholder="Semua project",
        )

start_date = min_date
end_date = max_date
if isinstance(date_range, tuple):
    if len(date_range) >= 1 and date_range[0] is not None:
        start_date = date_range[0]
    if len(date_range) >= 2 and date_range[1] is not None:
        end_date = date_range[1]
elif date_range is not None:
    start_date = end_date = date_range

filters = GraphFilterConfig(
    employee_names=(),
    projects=tuple(selected_projects),
    task_keys=(),
    states=(),
    note_keyword=None,
    start_date=start_date.isoformat(),
    end_date=end_date.isoformat(),
)
filtered = apply_graph_filters(source_dataframe, filters)
result = build_collaboration_graph(filtered)
mention_result = extract_collaboration_mentions(
    filtered,
    employee_roster=source_dataframe["employee"].dropna().astype(str).tolist(),
    aliases=load_employee_aliases(),
)
snapshot = analytics_service.build_snapshot(filters=filters)

if result.filtered_dataframe.empty:
    st.info("Scope yang dipilih tidak menghasilkan data. Ubah Nama Project atau Range Date.")
    st.stop()

summary = result.summary
scope_project = ", ".join(selected_projects) if selected_projects else "Semua project"
st.caption(f"{start_date:%d %b %Y} → {end_date:%d %b %Y} • {scope_project}")

a, b, c = st.columns(3)
a.metric("Karyawan", summary.employees)
b.metric("Relasi kolaborasi", summary.collaboration_links)
c.metric("Task kolaboratif", summary.collaborative_tasks)
d, e, f = st.columns(3)
d.metric("Project kolaboratif", summary.projects)
e.metric("Jam pada task kolaboratif", f"{summary.collaborative_hours:.2f}")
f.metric("Rata-rata kolaborator", f"{summary.average_collaborators:.2f}")

with st.sidebar:
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
    st.caption("Warna & ketebalan garis mengikuti frekuensi kolaborasi (jumlah task bersama).")
    show_labels = st.toggle(
        "Tampilkan nama karyawan",
        value=summary.employees <= 40,
        key="neural_graph_show_labels",
    )
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
            st.caption("Minimum task bersama: 1")

edges = result.edge_dataframe.copy()
if not edges.empty:
    edges = edges[edges["shared_task_count"] >= min_shared_tasks].reset_index(drop=True)

display_graph = result.graph.copy()
for source, target in list(display_graph.edges):
    keep = False
    if not edges.empty:
        keep = bool(
            (
                ((edges["source"] == source) & (edges["target"] == target))
                | ((edges["source"] == target) & (edges["target"] == source))
            ).any()
        )
    if not keep:
        display_graph.remove_edge(source, target)

directional_signals = build_visible_directional_signals(mention_result.directional_dataframe, edges)
acknowledgement_insights = build_acknowledgement_insights(
    result.edge_dataframe,
    mention_result.directional_dataframe,
)
mention_diagnostics = build_mention_diagnostics(filtered, mention_result, directional_signals)

st.subheader("Peta kolaborasi interaktif")
st.caption(
    "Garis tetap menunjukkan shared task. Marker chevron bergerak mengikuti arah penyebutan pada Note: dari pemilik "
    "timesheet menuju karyawan yang disebut. Jika kedua pihak saling menyebut, dua marker bergerak berlawanan sebagai "
    "dua evidence yang berbeda."
)
st.caption(
    f"Extraction diagnostics: {mention_diagnostics['notes_scanned']:,} Note dipindai • "
    f"{mention_diagnostics['notes_with_accepted_evidence']:,} Note punya evidence • "
    f"{mention_diagnostics['accepted_evidence']:,} evidence diterima • "
    f"{mention_diagnostics['directional_pairs']:,} arah acknowledgement • "
    f"{mention_diagnostics['visible_signals']:,} signal terlihat."
)
if mention_diagnostics["visible_signals"] == 0:
    st.caption(
        "Jika garis terlihat tetapi signal = 0, Note pada scope aktif belum menghasilkan acknowledgement yang cocok "
        "dengan shared-task edge yang sedang tampil. Nama satu kata yang unik di roster sekarang diterima; nama ambigu tetap ditolak."
    )
if result.summary.collaboration_links == 0:
    st.info("Tidak ada task yang dikerjakan oleh lebih dari satu karyawan pada scope aktif. Node tetap ditampilkan tanpa garis.")

sigma_html = build_sigma_html(
    display_graph,
    result.node_dataframe,
    edges,
    node_size_metric=node_size_metric,
    edge_width_metric="shared_task_count",
    show_labels=show_labels,
)
sigma_html = inject_pinball_effect(sigma_html, directional_signals)
components.html(sigma_html, height=835, scrolling=False)

with st.expander("Cara membaca Collaboration Graph", expanded=False):
    st.markdown(
        """
- **Node/dot besar = karyawan.**
- **Garis = dua karyawan mengerjakan `task_key` yang sama** pada Nama Project/Range Date aktif, walaupun tanggal pengerjaannya berbeda.
- **Warna & ketebalan garis = frekuensi kolaborasi**, dihitung dari jumlah task bersama untuk pasangan karyawan tersebut.
- **Bar scale** menunjukkan rentang frekuensi kolaborasi dari paling sedikit ke paling banyak pada scope aktif.
- **Chevron/arrowhead satu arah = penyebutan kolaborator pada Note timesheet.** Source adalah pemilik timesheet; ujung marker menunjuk ke karyawan yang disebut secara deterministic dengan confidence minimal 90%.
- **Nama satu kata yang unik di seluruh roster** diterima dengan confidence 92%. Jika token yang sama dimiliki lebih dari satu karyawan, alias tersebut dianggap ambigu dan tidak menghasilkan signal.
- Jika **A menyebut B** tetapi B tidak menyebut A, hanya ada marker **A → B**. Jika keduanya saling menyebut, dua directional marker berjalan berlawanan.
- Saat **hover/klik node**, marker pada relasi node tersebut dibuat lebih tegas sementara marker lain diredupkan agar jalur aktif lebih mudah dibaca.
- Satu target hanya dihitung **sekali per timesheet entry**, walaupun namanya disebut berulang kali pada Note yang sama.
- Alias/nickname eksplisit yang tidak berasal dari nama canonical dapat dikonfigurasi di `config/employee_aliases.json`.
- Animasi dibatasi maksimum **120 directional signal terkuat** dan memakai adaptive frame rate agar tetap ringan pada graph padat.
- **Mention-only** (ada penyebutan tetapi tidak ada shared task) tetap masuk analisis acknowledgement, tetapi belum divisualisasikan sebagai garis agar semantic garis tetap konsisten.
- **Ukuran node** dapat diganti dari sidebar.
- Acknowledgement reciprocity adalah sinyal pola dokumentasi kolaborasi, **bukan penilaian kualitas atau performa individu**.
"""
    )

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

with st.expander("Directional acknowledgement", expanded=False):
    if acknowledgement_insights.empty:
        st.info("Belum ada shared-task atau acknowledgement evidence pada scope aktif.")
    else:
        insight_table = acknowledgement_insights.copy()
        insight_table["acknowledgement_reciprocity"] = (
            insight_table["acknowledgement_reciprocity"].astype(float) * 100
        ).round(1)
        insight_table = insight_table.rename(
            columns={
                "employee_a": "Karyawan A",
                "employee_b": "Karyawan B",
                "shared_task_count": "Shared task",
                "a_to_b_count": "A → B",
                "b_to_a_count": "B → A",
                "acknowledgement_reciprocity": "Reciprocity (%)",
                "evidence_type": "Evidence type",
            }
        )
        st.dataframe(insight_table, use_container_width=True, hide_index=True)

    if not mention_result.directional_dataframe.empty:
        st.markdown("**Evidence arah dari Note**")
        direction_table = mention_result.directional_dataframe.copy().rename(
            columns={
                "source_employee": "Source",
                "target_employee": "Target",
                "acknowledgement_entry_count": "Timesheet evidence",
                "unique_task_count": "Task unik",
                "unique_project_count": "Project unik",
                "first_date": "Pertama",
                "last_date": "Terakhir",
            }
        )
        st.dataframe(direction_table, use_container_width=True, hide_index=True)

with st.expander("Detail karyawan", expanded=False):
    table = result.node_dataframe.copy()
    if not table.empty:
        for column in ["collaborators", "top_collaborators", "top_tasks"]:
            table[column] = table[column].map(lambda values: ", ".join(values))
    st.dataframe(table, use_container_width=True, hide_index=True)
