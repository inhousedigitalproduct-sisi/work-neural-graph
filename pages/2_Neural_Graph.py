from __future__ import annotations

from uuid import uuid4

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from src.analytics.service import AnalyticsService
from src.graph.builder import GraphFilterConfig, apply_graph_filters
from src.graph.collaboration import (
    build_collaboration_clusters,
    build_key_connectors,
    build_low_connectivity,
    build_ranked_collaborators,
    build_strongest_pairs,
)
from src.graph.collaboration_mentions import extract_collaboration_mentions, load_employee_aliases
from src.graph.note_collaboration import apply_note_evidence_threshold, build_note_collaboration_graph
from src.graph.sigma_renderer import build_sigma_html
from src.services import TimesheetDataService
from src.ui.components import render_analytics_summary
from src.utils.config import get_config


config = get_config()
dataset_service = TimesheetDataService(config.db_path)
analytics_service = AnalyticsService(config.db_path)

st.title("Neural Graph — Kolaborasi")
st.caption(
    "Eksplorasi hubungan antar-karyawan berdasarkan penyebutan nama rekan secara eksplisit pada Note timesheet. "
    "Task dan Project dipakai sebagai konteks evidence, bukan sebagai pembentuk relasi."
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
if filtered.empty:
    st.info("Scope yang dipilih tidak menghasilkan data. Ubah Nama Project atau Range Date.")
    st.stop()

# The mention roster must follow the active project/date scope. Using the full
# dataset roster allowed a note inside the selected project to create a node for
# an employee who had no timesheet row in that filtered scope.
scoped_employee_roster = filtered["employee"].dropna().astype(str).tolist()
mention_result = extract_collaboration_mentions(
    filtered,
    employee_roster=scoped_employee_roster,
    aliases=load_employee_aliases(),
)
result = build_note_collaboration_graph(filtered, mention_result, include_isolated=True)
snapshot = analytics_service.build_snapshot(filters=filters)

with st.sidebar:
    st.subheader("Collaboration Graph")
    node_size_metric = st.selectbox(
        "Ukuran node",
        ["collaborator_count", "collaborative_task_count", "project_count", "collaborative_hours"],
        format_func=lambda value: {
            "collaborator_count": "Jumlah kolaborator",
            "collaborative_task_count": "Evidence Note",
            "project_count": "Project pada evidence",
            "collaborative_hours": "Jam terkait evidence",
        }[value],
        key="neural_graph_node_size_metric",
    )
    st.caption("Warna & ketebalan garis mengikuti jumlah evidence penyebutan nama pada Note.")

    min_evidence = 1
    slider_key = "neural_graph_min_note_evidence"
    if not result.edge_dataframe.empty:
        maximum = max(1, int(result.edge_dataframe["shared_task_count"].max()))
        current = int(st.session_state.get(slider_key, 1) or 1)
        st.session_state[slider_key] = min(max(current, 1), maximum)
        if maximum > 1:
            min_evidence = st.slider(
                "Minimum evidence Note",
                min_value=1,
                max_value=maximum,
                key=slider_key,
            )
        else:
            st.session_state[slider_key] = 1
            st.caption("Minimum evidence Note: 1")
    else:
        st.session_state[slider_key] = 1
        st.caption("Minimum evidence Note: 1")

    show_isolated = st.toggle(
        "Show Isolated",
        value=False,
        key="neural_graph_show_isolated",
        help="Menampilkan employee yang tidak memiliki evidence penyebutan nama pada threshold aktif.",
    )

active_result = apply_note_evidence_threshold(result, min_evidence, include_isolated=False)
all_threshold_result = apply_note_evidence_threshold(result, min_evidence, include_isolated=True)
display_result = all_threshold_result if show_isolated else active_result

with st.sidebar:
    show_labels = st.toggle(
        "Tampilkan nama karyawan",
        value=display_result.summary.employees <= 40,
        key="neural_graph_show_labels",
    )

summary = display_result.summary
scope_project = ", ".join(selected_projects) if selected_projects else "Semua project"
st.caption(
    f"{start_date:%d %b %Y} → {end_date:%d %b %Y} • {scope_project} • "
    f"minimum {min_evidence} evidence Note"
)

a, b, c = st.columns(3)
a.metric("Karyawan", summary.employees)
b.metric("Relasi evidence", summary.collaboration_links)
c.metric("Evidence kolaborasi (Note)", summary.collaborative_tasks)
d, e, f = st.columns(3)
d.metric("Project pada evidence", summary.projects)
e.metric("Jam terkait evidence", f"{summary.collaborative_hours:.2f}")
f.metric("Rata-rata kolaborator", f"{summary.average_collaborators:.2f}")

st.subheader("Peta kolaborasi interaktif")
st.caption(
    "Garis hanya terbentuk dari penyebutan nama karyawan pada Note. Memilih employee dari pencarian akan memfokuskan kamera "
    "ke dot employee tersebut tanpa menghilangkan konteks relasi langsungnya."
)
if active_result.summary.collaboration_links == 0:
    if show_isolated:
        st.info("Belum ada evidence penyebutan kolaborator pada Note untuk threshold aktif. Employee tetap ditampilkan karena Show Isolated aktif.")
    else:
        st.info("Belum ada evidence penyebutan kolaborator pada Note untuk threshold aktif. Turunkan threshold atau aktifkan Show Isolated.")

sigma_html = build_sigma_html(
    display_result.graph,
    display_result.node_dataframe,
    display_result.edge_dataframe,
    node_size_metric=node_size_metric,
    edge_width_metric="shared_task_count",
    show_labels=show_labels,
)
# Force a fresh iframe document on every Streamlit rerun. This prevents the
# long-lived PixiJS canvas from keeping the previous graph after scope filters,
# threshold, isolated visibility, node sizing, or label settings change.
render_nonce = uuid4().hex
sigma_html = sigma_html.replace("<body>", f'<body data-render-nonce="{render_nonce}">', 1)
components.html(sigma_html, height=835, scrolling=False)

with st.expander("Cara membaca Collaboration Graph", expanded=False):
    st.markdown(
        """
- **Node = karyawan.**
- **Garis = ada evidence eksplisit pada Note**, yaitu pemilik timesheet menyebut nama employee lain yang lolos deterministic matching.
- **Task yang sama tidak lagi otomatis dianggap kolaborasi.** Task dan Project hanya menjadi konteks dari evidence Note.
- **Warna & ketebalan garis = jumlah evidence Note** pada pasangan tersebut.
- **Minimum evidence Note** memfilter relasi dan menghitung ulang node, collaborator, ranking, cluster, search, detail, dan summary graph.
- **Show Isolated** menampilkan employee tanpa evidence relasi pada threshold aktif.
- Klik atau cari employee untuk menonjolkan relasi langsung. Search memindahkan kamera ke posisi dot employee pada koordinat display PixiJS.
- Nama satu kata yang unik di seluruh roster diterima dengan confidence 92% mulai dari 3 karakter; token ambigu ditolak.
- Satu target dihitung maksimum sekali per timesheet entry meskipun namanya disebut berulang pada Note yang sama.
- Tidak adanya evidence Note berarti **tidak ditemukan evidence penyebutan kolaborator**, bukan bukti bahwa employee tidak berkolaborasi.
"""
    )

st.subheader("Collaboration Insights")
ranked = build_ranked_collaborators(active_result.node_dataframe)
strongest = build_strongest_pairs(active_result.edge_dataframe)
connectors = build_key_connectors(active_result.graph)
low_connectivity = build_low_connectivity(all_threshold_result.node_dataframe)
clusters = build_collaboration_clusters(active_result.graph)

rank_tab, pair_tab, connector_tab, low_tab, cluster_tab = st.tabs(
    ["Top Collaborators", "Strongest Pairs", "Key Connectors", "Low Connectivity", "Clusters"]
)
with rank_tab:
    st.caption("Ranking mengutamakan breadth relasi, lalu jumlah evidence Note, jam terkait evidence, dan project.")
    table = ranked.rename(
        columns={
            "employee": "Karyawan",
            "collaborator_count": "Collaborators",
            "collaborative_task_count": "Evidence Note",
            "collaborative_hours": "Related evidence hours",
            "project_count": "Projects",
        }
    )
    st.dataframe(table, use_container_width=True, hide_index=True)

with pair_tab:
    st.caption("Pasangan dengan evidence penyebutan nama terbanyak pada threshold aktif.")
    table = strongest.copy()
    if not table.empty:
        table["projects"] = table["projects"].map(lambda values: ", ".join(values))
        table["shared_tasks"] = table["shared_tasks"].map(lambda values: ", ".join(values))
    table = table.rename(
        columns={
            "source": "Karyawan A",
            "target": "Karyawan B",
            "shared_task_count": "Evidence Note",
            "related_hours": "Related hours",
            "projects": "Projects",
            "shared_tasks": "Task context",
        }
    )
    st.dataframe(table, use_container_width=True, hide_index=True)

with connector_tab:
    st.caption("Connector score memakai weighted betweenness centrality pada graph evidence Note; bukan skor performa.")
    table = connectors.rename(
        columns={
            "employee": "Karyawan",
            "connector_score": "Connector score",
            "collaborator_count": "Collaborators",
        }
    )
    st.dataframe(table, use_container_width=True, hide_index=True)

with low_tab:
    st.caption("Konektivitas rendah berarti evidence Note yang menghubungkan employee relatif sedikit pada scope aktif; bukan penilaian performa.")
    table = low_connectivity.rename(
        columns={
            "employee": "Karyawan",
            "collaborator_count": "Collaborators",
            "collaborative_task_count": "Evidence Note",
            "project_count": "Projects",
        }
    )
    st.dataframe(table, use_container_width=True, hide_index=True)

with cluster_tab:
    st.caption("Community/cluster dihitung dari hubungan penyebutan nama pada Note.")
    table = clusters.copy()
    if not table.empty:
        table["members"] = table["members"].map(lambda values: ", ".join(values))
    table = table.rename(
        columns={
            "cluster": "Cluster",
            "size": "Members",
            "members": "Karyawan",
            "internal_links": "Internal links",
            "shared_task_strength": "Evidence strength",
        }
    )
    st.dataframe(table, use_container_width=True, hide_index=True)

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

with st.expander("Relasi kolaborasi berbasis Note", expanded=False):
    table = display_result.edge_dataframe.drop(columns=["shared_task_keys", "evidence_entry_ids"], errors="ignore").copy()
    if not table.empty:
        table["shared_tasks"] = table["shared_tasks"].map(lambda values: ", ".join(values))
        table["projects"] = table["projects"].map(lambda values: ", ".join(values))
        table = table.rename(
            columns={
                "source": "Karyawan A",
                "target": "Karyawan B",
                "shared_task_count": "Evidence Note",
                "shared_tasks": "Task context",
                "projects": "Projects",
                "related_hours": "Related hours",
                "a_to_b_count": "A menyebut B",
                "b_to_a_count": "B menyebut A",
            }
        )
    st.dataframe(table, use_container_width=True, hide_index=True)

with st.expander("Evidence penyebutan dari Note", expanded=False):
    st.caption("Source adalah pemilik timesheet; target adalah employee yang disebut pada Note.")
    if mention_result.directional_dataframe.empty:
        st.info("Belum ada evidence penyebutan nama employee lain pada Note di scope aktif.")
    else:
        direction_table = mention_result.directional_dataframe.copy().rename(
            columns={
                "source_employee": "Pemilik timesheet",
                "target_employee": "Nama yang disebut",
                "acknowledgement_entry_count": "Jumlah evidence",
                "unique_task_count": "Task context unik",
                "unique_project_count": "Project unik",
                "first_date": "Pertama",
                "last_date": "Terakhir",
            }
        )
        st.dataframe(direction_table, use_container_width=True, hide_index=True)

with st.expander("Detail karyawan", expanded=False):
    table = display_result.node_dataframe.copy()
    if not table.empty:
        for column in ["collaborators", "top_collaborators", "top_tasks"]:
            table[column] = table[column].map(lambda values: ", ".join(values))
        table = table.rename(
            columns={
                "employee": "Karyawan",
                "collaborator_count": "Collaborators",
                "collaborative_task_count": "Evidence Note",
                "project_count": "Projects",
                "collaborative_hours": "Related evidence hours",
                "collaborators": "Collaborator list",
                "top_collaborators": "Top collaborators",
                "top_tasks": "Task context",
            }
        )
    st.dataframe(table, use_container_width=True, hide_index=True)
