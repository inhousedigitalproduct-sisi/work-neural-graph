from __future__ import annotations

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from src.analytics.service import AnalyticsService
from src.graph.builder import GraphFilterConfig, apply_graph_filters
from src.graph.collaboration import (
    apply_collaboration_threshold,
    build_collaboration_clusters,
    build_collaboration_graph,
    build_key_connectors,
    build_low_connectivity,
    build_ranked_collaborators,
    build_strongest_pairs,
)
from src.graph.collaboration_mentions import (
    build_acknowledgement_insights,
    extract_collaboration_mentions,
    load_employee_aliases,
)
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

    min_shared_tasks = 1
    slider_key = "neural_graph_min_shared_tasks"
    if not result.edge_dataframe.empty:
        maximum = max(1, int(result.edge_dataframe["shared_task_count"].max()))
        current = int(st.session_state.get(slider_key, 1) or 1)
        st.session_state[slider_key] = min(max(current, 1), maximum)
        if maximum > 1:
            min_shared_tasks = st.slider(
                "Minimum task bersama",
                min_value=1,
                max_value=maximum,
                key=slider_key,
            )
        else:
            st.session_state[slider_key] = 1
            st.caption("Minimum task bersama: 1")
    else:
        st.session_state[slider_key] = 1
        st.caption("Minimum task bersama: 1")

    show_isolated = st.toggle(
        "Show Isolated",
        value=False,
        key="neural_graph_show_isolated",
        help="Secara default hanya karyawan yang masih memiliki relasi pada threshold aktif yang ditampilkan.",
    )

active_result = apply_collaboration_threshold(result, min_shared_tasks, include_isolated=False)
all_threshold_result = apply_collaboration_threshold(result, min_shared_tasks, include_isolated=True)
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
    f"minimum {min_shared_tasks} task bersama"
)

a, b, c = st.columns(3)
a.metric("Karyawan", summary.employees)
b.metric("Relasi kolaborasi", summary.collaboration_links)
c.metric("Task kolaboratif", summary.collaborative_tasks)
d, e, f = st.columns(3)
d.metric("Project kolaboratif", summary.projects)
e.metric("Jam pada task kolaboratif", f"{summary.collaborative_hours:.2f}")
f.metric("Rata-rata kolaborator", f"{summary.average_collaborators:.2f}")

acknowledgement_insights = build_acknowledgement_insights(
    result.edge_dataframe,
    mention_result.directional_dataframe,
)

st.subheader("Peta kolaborasi interaktif")
st.caption(
    "Mode eksplorasi ringan: node dibuat compact, relasi tetap menonjol, dan zoom diperdalam untuk membaca jaringan padat. "
    "Metric node, detail, search, dan summary mengikuti Minimum task bersama yang aktif."
)
if active_result.summary.collaboration_links == 0:
    if show_isolated:
        st.info("Threshold aktif tidak menghasilkan relasi. Karyawan tanpa relasi tetap ditampilkan karena Show Isolated aktif.")
    else:
        st.info("Threshold aktif tidak menghasilkan relasi. Turunkan Minimum task bersama atau aktifkan Show Isolated.")

sigma_html = build_sigma_html(
    display_result.graph,
    display_result.node_dataframe,
    display_result.edge_dataframe,
    node_size_metric=node_size_metric,
    edge_width_metric="shared_task_count",
    show_labels=show_labels,
)
# Isolated visibility is controlled by Streamlit so graph metrics/search/detail stay in sync.
sigma_html = sigma_html.replace(
    '<button id="isolate">Hide Isolated</button>',
    '<button id="isolate" style="display:none" aria-hidden="true">Hide Isolated</button>',
)
components.html(sigma_html, height=835, scrolling=False)

with st.expander("Cara membaca Collaboration Graph", expanded=False):
    st.markdown(
        """
- **Node kecil = karyawan.** Ukuran node mengikuti metric yang dipilih di sidebar dan dihitung ulang setelah threshold aktif.
- **Garis = dua karyawan mengerjakan `task_key` yang sama** pada Nama Project/Range Date aktif, walaupun tanggal pengerjaannya berbeda.
- **Minimum task bersama** memfilter relasi dan sekaligus menghitung ulang node, collaborator, shared task, hours, project, search, detail, dan summary graph.
- **Show Isolated** menampilkan kembali karyawan yang tidak memiliki relasi pada threshold aktif; default-nya disembunyikan.
- **Warna & ketebalan garis = frekuensi kolaborasi**, dihitung dari jumlah task bersama untuk pasangan karyawan tersebut.
- **Bar scale** menunjukkan rentang frekuensi kolaborasi dari paling sedikit ke paling banyak pada graph aktif.
- Gunakan **scroll untuk zoom**, termasuk zoom-in lebih jauh pada cluster padat; drag canvas untuk pan dan drag node untuk merapikan posisi lokal.
- Klik atau cari karyawan untuk menonjolkan relasi langsung tanpa membesarkan node secara berlebihan.
- Data penyebutan nama pada Note tetap dianalisis di bagian **Penyebutan Kolaborator (Note)** di bawah graph; data tersebut tidak dianimasikan pada network.
- **Nama satu kata yang unik di seluruh roster** diterima dengan confidence 92% mulai dari 3 karakter. Jika token yang sama dimiliki lebih dari satu karyawan, alias tersebut dianggap ambigu.
- Satu target hanya dihitung **sekali per timesheet entry**, walaupun namanya disebut berulang kali pada Note yang sama.
- Alias/nickname eksplisit yang tidak berasal dari nama canonical dapat dikonfigurasi di `config/employee_aliases.json`.
- Reciprocity pada penyebutan nama adalah sinyal pola dokumentasi kolaborasi, **bukan penilaian kualitas atau performa individu**.
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
    st.caption("Ranking mengutamakan breadth kolaborasi, lalu shared task, jam kolaboratif, dan project.")
    table = ranked.rename(
        columns={
            "employee": "Karyawan",
            "collaborator_count": "Collaborators",
            "collaborative_task_count": "Shared tasks",
            "collaborative_hours": "Collaborative hours",
            "project_count": "Projects",
        }
    )
    st.dataframe(table, use_container_width=True, hide_index=True)

with pair_tab:
    st.caption("Pasangan dengan frekuensi shared task terkuat pada threshold aktif.")
    table = strongest.copy()
    if not table.empty:
        table["projects"] = table["projects"].map(lambda values: ", ".join(values))
        table["shared_tasks"] = table["shared_tasks"].map(lambda values: ", ".join(values))
    table = table.rename(
        columns={
            "source": "Karyawan A",
            "target": "Karyawan B",
            "shared_task_count": "Shared tasks",
            "related_hours": "Related hours",
            "projects": "Projects",
            "shared_tasks": "Tasks",
        }
    )
    st.dataframe(table, use_container_width=True, hide_index=True)

with connector_tab:
    st.caption("Connector score memakai weighted betweenness centrality untuk menemukan penghubung antarbagian jaringan; bukan skor performa.")
    table = connectors.rename(
        columns={
            "employee": "Karyawan",
            "connector_score": "Connector score",
            "collaborator_count": "Collaborators",
        }
    )
    st.dataframe(table, use_container_width=True, hide_index=True)

with low_tab:
    st.caption("Menunjukkan konektivitas graph yang rendah atau isolated pada scope/threshold aktif; bukan penilaian performa individu.")
    table = low_connectivity.rename(
        columns={
            "employee": "Karyawan",
            "collaborator_count": "Collaborators",
            "collaborative_task_count": "Shared tasks",
            "project_count": "Projects",
        }
    )
    st.dataframe(table, use_container_width=True, hide_index=True)

with cluster_tab:
    st.caption("Community/cluster dihitung dari graph aktif sehingga warna cluster dapat dibaca sebagai insight, bukan hanya dekorasi.")
    table = clusters.copy()
    if not table.empty:
        table["members"] = table["members"].map(lambda values: ", ".join(values))
    table = table.rename(
        columns={
            "cluster": "Cluster",
            "size": "Members",
            "members": "Karyawan",
            "internal_links": "Internal links",
            "shared_task_strength": "Shared-task strength",
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

with st.expander("Relasi kolaborasi", expanded=False):
    table = display_result.edge_dataframe.drop(columns=["shared_task_keys"], errors="ignore").copy()
    if not table.empty:
        table["shared_tasks"] = table["shared_tasks"].map(lambda values: ", ".join(values))
        table["projects"] = table["projects"].map(lambda values: ", ".join(values))
    st.dataframe(table, use_container_width=True, hide_index=True)

with st.expander("Penyebutan Kolaborator (Note)", expanded=False):
    st.caption(
        "Bagian ini memakai scope Project/Range Date dan tetap memisahkan shared-task collaboration dari penyebutan nama rekan secara eksplisit di Note."
    )
    if acknowledgement_insights.empty:
        st.info("Belum ada shared-task atau evidence penyebutan nama pada scope aktif.")
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
                "a_to_b_count": "A menyebut B",
                "b_to_a_count": "B menyebut A",
                "acknowledgement_reciprocity": "Reciprocity (%)",
                "evidence_type": "Pola evidence",
            }
        )
        st.dataframe(insight_table, use_container_width=True, hide_index=True)

    if not mention_result.directional_dataframe.empty:
        st.markdown("**Evidence penyebutan dari Note**")
        direction_table = mention_result.directional_dataframe.copy().rename(
            columns={
                "source_employee": "Pemilik timesheet",
                "target_employee": "Nama yang disebut",
                "acknowledgement_entry_count": "Jumlah timesheet",
                "unique_task_count": "Task unik",
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
    st.dataframe(table, use_container_width=True, hide_index=True)
