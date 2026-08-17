from __future__ import annotations

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from src.analytics.service import AnalyticsService
from src.graph.builder import GraphFilterConfig, apply_graph_filters
from src.graph.collaboration import build_collaboration_graph
from src.graph.sigma_renderer import build_sigma_html
from src.services import TimesheetDataService
from src.ui.components import render_analytics_summary
from src.utils.config import get_config

config = get_config()
dataset_service = TimesheetDataService(config.db_path)
analytics_service = AnalyticsService(config.db_path)

NEURON_SIGNAL_STYLE = """
    #neuron-signal-layer {
      position:absolute;
      inset:0;
      width:100%;
      height:100%;
      z-index:6;
      pointer-events:none;
    }
"""

NEURON_SIGNAL_SCRIPT = r"""
    const neuronLayer = document.getElementById("neuron-signal-layer");
    const neuronStage = document.getElementById("stage");
    const neuronContext = neuronLayer ? neuronLayer.getContext("2d") : null;
    const prefersReducedMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches ?? false;
    let neuronDpr = 1;
    let lastNeuronFrame = 0;

    function hexToRgba(hex, alpha) {
      const normalized = String(hex || "#fb923c").replace("#", "");
      if (!/^[0-9a-fA-F]{6}$/.test(normalized)) return `rgba(251,146,60,${alpha})`;
      const value = parseInt(normalized, 16);
      const r = (value >> 16) & 255;
      const g = (value >> 8) & 255;
      const b = value & 255;
      return `rgba(${r},${g},${b},${alpha})`;
    }

    function resizeNeuronLayer() {
      if (!neuronLayer || !neuronStage || !neuronContext) return;
      const rect = neuronStage.getBoundingClientRect();
      neuronDpr = Math.min(window.devicePixelRatio || 1, 2);
      const width = Math.max(1, Math.round(rect.width * neuronDpr));
      const height = Math.max(1, Math.round(rect.height * neuronDpr));
      if (neuronLayer.width !== width || neuronLayer.height !== height) {
        neuronLayer.width = width;
        neuronLayer.height = height;
        neuronLayer.style.width = `${rect.width}px`;
        neuronLayer.style.height = `${rect.height}px`;
      }
      neuronContext.setTransform(neuronDpr, 0, 0, neuronDpr, 0, 0);
    }

    function edgePhase(edgeKey) {
      let hash = 0;
      const text = String(edgeKey);
      for (let i = 0; i < text.length; i += 1) hash = ((hash << 5) - hash + text.charCodeAt(i)) | 0;
      return Math.abs(hash % 1000) / 1000;
    }

    function collaborationRatio(value) {
      const scale = data.collaboration_scale || {min: 0, max: 0};
      const low = Number(scale.min || 0);
      const high = Number(scale.max || 0);
      if (high <= low) return 0.55;
      return Math.max(0, Math.min(1, (Number(value || 0) - low) / (high - low)));
    }

    function drawNeuronSignals(now) {
      if (!neuronContext || !neuronLayer || !neuronStage) return;
      window.requestAnimationFrame(drawNeuronSignals);

      // ~30 FPS is enough for a soft pulse and keeps dense graphs responsive.
      if (now - lastNeuronFrame < 32) return;
      lastNeuronFrame = now;
      resizeNeuronLayer();

      const rect = neuronStage.getBoundingClientRect();
      neuronContext.clearRect(0, 0, rect.width, rect.height);
      const focusNode = selectedNode || hoveredNode;
      if (!focusNode || !graph.hasNode(focusNode)) return;

      graph.edges(focusNode).forEach(edgeKey => {
        const attrs = graph.getEdgeAttributes(edgeKey);
        const [source, target] = graph.extremities(edgeKey);
        const sourceAttrs = graph.getNodeAttributes(source);
        const targetAttrs = graph.getNodeAttributes(target);
        const sourcePoint = renderer.graphToViewport({x: sourceAttrs.x, y: sourceAttrs.y});
        const targetPoint = renderer.graphToViewport({x: targetAttrs.x, y: targetAttrs.y});
        const count = Number(attrs.collaboration_count || attrs.shared_task_count || 1);
        const intensity = collaborationRatio(count);
        const signalColor = attrs.color || "#fb923c";

        neuronContext.save();
        neuronContext.beginPath();
        neuronContext.moveTo(sourcePoint.x, sourcePoint.y);
        neuronContext.lineTo(targetPoint.x, targetPoint.y);
        neuronContext.lineCap = "round";
        neuronContext.lineWidth = 1.1 + intensity * 1.9;
        neuronContext.strokeStyle = hexToRgba(signalColor, 0.12 + intensity * 0.20);
        neuronContext.shadowColor = signalColor;
        neuronContext.shadowBlur = 8 + intensity * 10;
        neuronContext.stroke();

        if (!prefersReducedMotion) {
          const speed = 0.00020 + intensity * 0.00016;
          const phase = (now * speed + edgePhase(edgeKey)) % 1;
          // Triangle wave: 0 -> 1 -> 0 creates a bidirectional neuron-like pulse.
          const travel = 1 - Math.abs(1 - 2 * phase);
          const x = sourcePoint.x + (targetPoint.x - sourcePoint.x) * travel;
          const y = sourcePoint.y + (targetPoint.y - sourcePoint.y) * travel;
          const radius = 2.0 + intensity * 1.7;

          neuronContext.beginPath();
          neuronContext.arc(x, y, radius, 0, Math.PI * 2);
          neuronContext.fillStyle = hexToRgba("#fff7ed", 0.88);
          neuronContext.shadowColor = signalColor;
          neuronContext.shadowBlur = 12 + intensity * 14;
          neuronContext.fill();
        }
        neuronContext.restore();
      });
    }

    if (neuronLayer && neuronStage && neuronContext) {
      resizeNeuronLayer();
      new ResizeObserver(resizeNeuronLayer).observe(neuronStage);
      window.requestAnimationFrame(drawNeuronSignals);
    }
"""


def inject_neuron_signal_effect(html: str) -> str:
    """Add a lightweight animated pulse overlay to active Sigma collaboration edges."""
    html = html.replace("</style>", f"{NEURON_SIGNAL_STYLE}\n  </style>", 1)
    html = html.replace(
        '<div id="sigma-container"></div>',
        '<div id="sigma-container"></div>\n    <canvas id="neuron-signal-layer" aria-hidden="true"></canvas>',
        1,
    )
    html = html.replace("  </script>", f"{NEURON_SIGNAL_SCRIPT}\n  </script>", 1)
    return html


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

st.subheader("Peta kolaborasi interaktif")
st.caption(
    "Klik atau hover node untuk mengaktifkan pulse seperti sinyal neuron pada relasi aktif, drag node untuk mengatur posisi, "
    "scroll untuk zoom, dan hover garis untuk melihat task/project bersama. Bar scale menunjukkan frekuensi kolaborasi."
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
sigma_html = inject_neuron_signal_effect(sigma_html)
components.html(sigma_html, height=835, scrolling=False)

with st.expander("Cara membaca Collaboration Graph", expanded=False):
    st.markdown(
        """
- **Node/dot = karyawan.**
- **Garis = dua karyawan mengerjakan `task_key` yang sama** pada Nama Project/Range Date aktif, walaupun tanggal pengerjaannya berbeda.
- **Warna & ketebalan garis = frekuensi kolaborasi**, dihitung dari jumlah task bersama untuk pasangan karyawan tersebut.
- **Bar scale** menunjukkan rentang frekuensi kolaborasi dari paling sedikit ke paling banyak pada scope aktif.
- **Klik atau hover node** mengaktifkan soft glow dan pulse bolak-balik pada garis yang terhubung, seperti impuls neuron. Intensitasnya mengikuti frekuensi kolaborasi.
- **Hover garis** untuk melihat task, project, dan total jam yang menjadi dasar relasi.
- **Ukuran node** dapat diganti dari sidebar.
- Animasi adalah bantuan visual untuk menonjolkan relasi aktif; warna node tetap menunjukkan community/cluster dan bukan penilaian performa individu.
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

with st.expander("Detail karyawan", expanded=False):
    table = result.node_dataframe.copy()
    if not table.empty:
        for column in ["collaborators", "top_collaborators", "top_tasks"]:
            table[column] = table[column].map(lambda values: ", ".join(values))
    st.dataframe(table, use_container_width=True, hide_index=True)
