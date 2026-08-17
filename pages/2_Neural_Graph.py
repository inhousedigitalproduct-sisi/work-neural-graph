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
      mix-blend-mode:screen;
    }
"""

NEURON_SIGNAL_SCRIPT = r"""
    const neuronLayer = document.getElementById("neuron-signal-layer");
    const neuronStage = document.getElementById("stage");
    const neuronContext = neuronLayer ? neuronLayer.getContext("2d") : null;
    const prefersReducedMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches ?? false;
    const MAX_AMBIENT_EDGES = 160;
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
      neuronDpr = Math.min(window.devicePixelRatio || 1, 1.5);
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

    const signalEdges = data.edges.map(edge => {
      const count = Number(edge.collaboration_count || edge.shared_task_count || 1);
      return {
        key: edge.id,
        source: edge.source,
        target: edge.target,
        color: edge.color || "#fb923c",
        count,
        intensity: collaborationRatio(count),
        phase: edgePhase(edge.id),
      };
    }).sort((a, b) => b.count - a.count);

    const ambientEdges = signalEdges.slice(0, MAX_AMBIENT_EDGES);
    const edgesByNode = new Map();
    signalEdges.forEach(edge => {
      if (!edgesByNode.has(edge.source)) edgesByNode.set(edge.source, []);
      if (!edgesByNode.has(edge.target)) edgesByNode.set(edge.target, []);
      edgesByNode.get(edge.source).push(edge);
      edgesByNode.get(edge.target).push(edge);
    });

    const frameInterval = signalEdges.length > 180 ? 62 : signalEdges.length > 90 ? 50 : 40;

    function pointOnEdge(sourcePoint, targetPoint, t) {
      return {
        x: sourcePoint.x + (targetPoint.x - sourcePoint.x) * t,
        y: sourcePoint.y + (targetPoint.y - sourcePoint.y) * t,
      };
    }

    function drawImpulse(sourcePoint, targetPoint, headT, direction, length, color, intensity, active) {
      const tailT = Math.max(0, Math.min(1, headT - direction * length));
      const coreT = Math.max(0, Math.min(1, headT - direction * length * 0.34));
      const tail = pointOnEdge(sourcePoint, targetPoint, tailT);
      const core = pointOnEdge(sourcePoint, targetPoint, coreT);
      const head = pointOnEdge(sourcePoint, targetPoint, headT);

      neuronContext.save();
      neuronContext.globalCompositeOperation = "lighter";
      neuronContext.lineCap = "round";

      // Broad luminous body. Strong shadow creates the electrical/neuron impression without a moving orb.
      neuronContext.beginPath();
      neuronContext.moveTo(tail.x, tail.y);
      neuronContext.lineTo(head.x, head.y);
      neuronContext.lineWidth = active ? 3.0 + intensity * 2.5 : 1.15 + intensity * 0.95;
      neuronContext.strokeStyle = hexToRgba(
        color,
        active ? 0.64 + intensity * 0.22 : 0.28 + intensity * 0.18,
      );
      neuronContext.shadowColor = color;
      neuronContext.shadowBlur = active ? 24 + intensity * 18 : 10 + intensity * 8;
      neuronContext.stroke();

      // Short white-hot core at the head makes the streak eye-catching while keeping it impulse-shaped.
      neuronContext.beginPath();
      neuronContext.moveTo(core.x, core.y);
      neuronContext.lineTo(head.x, head.y);
      neuronContext.lineWidth = active ? 1.55 + intensity * 0.85 : 0.72 + intensity * 0.42;
      neuronContext.strokeStyle = hexToRgba("#fff7ed", active ? 0.98 : 0.76);
      neuronContext.shadowColor = "#fff7ed";
      neuronContext.shadowBlur = active ? 16 + intensity * 12 : 7 + intensity * 5;
      neuronContext.stroke();
      neuronContext.restore();
    }

    function drawActiveEdgeGlow(sourcePoint, targetPoint, color, intensity) {
      neuronContext.save();
      neuronContext.globalCompositeOperation = "lighter";
      neuronContext.beginPath();
      neuronContext.moveTo(sourcePoint.x, sourcePoint.y);
      neuronContext.lineTo(targetPoint.x, targetPoint.y);
      neuronContext.lineCap = "round";
      neuronContext.lineWidth = 1.6 + intensity * 1.8;
      neuronContext.strokeStyle = hexToRgba(color, 0.22 + intensity * 0.18);
      neuronContext.shadowColor = color;
      neuronContext.shadowBlur = 14 + intensity * 14;
      neuronContext.stroke();
      neuronContext.restore();
    }

    function drawNeuronSignals(now) {
      if (!neuronContext || !neuronLayer || !neuronStage) return;
      window.requestAnimationFrame(drawNeuronSignals);
      if (document.hidden || prefersReducedMotion) return;
      if (now - lastNeuronFrame < frameInterval) return;
      lastNeuronFrame = now;
      resizeNeuronLayer();

      const rect = neuronStage.getBoundingClientRect();
      neuronContext.clearRect(0, 0, rect.width, rect.height);
      const focusNode = selectedNode || hoveredNode;
      const hasFocus = Boolean(focusNode && graph.hasNode(focusNode));
      const activeEdges = hasFocus ? (edgesByNode.get(focusNode) || []) : [];
      const activeKeys = new Set(activeEdges.map(edge => edge.key));
      const edgesToDraw = hasFocus
        ? ambientEdges.filter(edge => !activeKeys.has(edge.key)).concat(activeEdges)
        : ambientEdges;

      // A node can belong to many edges. Cache viewport conversion once per node, per frame.
      const pointCache = new Map();
      const viewportPoint = nodeId => {
        if (pointCache.has(nodeId)) return pointCache.get(nodeId);
        const attrs = graph.getNodeAttributes(nodeId);
        const point = renderer.graphToViewport({x: attrs.x, y: attrs.y});
        pointCache.set(nodeId, point);
        return point;
      };

      edgesToDraw.forEach(edge => {
        const sourcePoint = viewportPoint(edge.source);
        const targetPoint = viewportPoint(edge.target);
        const active = activeKeys.has(edge.key);

        if (active) drawActiveEdgeGlow(sourcePoint, targetPoint, edge.color, edge.intensity);

        const speed = active
          ? 0.00038 + edge.intensity * 0.00020
          : hasFocus
            ? 0.000075 + edge.intensity * 0.000035
            : 0.00012 + edge.intensity * 0.00006;
        const cycle = now * speed + edge.phase;
        const cycleIndex = Math.floor(cycle);
        const progress = cycle - cycleIndex;
        const direction = (cycleIndex + Math.floor(edge.phase * 10)) % 2 === 0 ? 1 : -1;
        const headT = direction === 1 ? progress : 1 - progress;
        const length = active ? 0.18 + edge.intensity * 0.08 : 0.09 + edge.intensity * 0.05;

        drawImpulse(
          sourcePoint,
          targetPoint,
          headT,
          direction,
          length,
          edge.color,
          edge.intensity,
          active,
        );
      });
    }

    if (neuronLayer && neuronStage && neuronContext && !prefersReducedMotion) {
      resizeNeuronLayer();
      new ResizeObserver(resizeNeuronLayer).observe(neuronStage);
      window.requestAnimationFrame(drawNeuronSignals);
    }
"""


def inject_neuron_signal_effect(html: str) -> str:
    """Add optimized ambient/focus neuron impulse streaks to Sigma collaboration edges."""
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
    interactive = st.toggle(
        "Interactive",
        value=False,
        key="neural_graph_interactive",
        help="ON menampilkan impuls neuron. OFF mematikan animasi untuk performa paling ringan.",
    )
    st.caption(
        "Impuls neuron ON — ambient + focus glow."
        if interactive
        else "Impuls neuron OFF — mode performa ringan."
    )
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
if interactive:
    st.caption(
        "Interactive ON: impuls neuron yang lebih bercahaya mengalir otomatis pada relasi terkuat; hover atau klik node "
        "memperkuat seluruh impuls relasi node tersebut. Pada graph padat, ambient animation dibatasi otomatis demi performa."
    )
else:
    st.caption(
        "Interactive OFF: graph tetap dapat di-hover, klik, drag, dan zoom tanpa overlay impuls agar penggunaan GPU/CPU lebih ringan."
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
if interactive:
    sigma_html = inject_neuron_signal_effect(sigma_html)
components.html(sigma_html, height=835, scrolling=False)

with st.expander("Cara membaca Collaboration Graph", expanded=False):
    st.markdown(
        """
- **Node/dot = karyawan.**
- **Garis = dua karyawan mengerjakan `task_key` yang sama** pada Nama Project/Range Date aktif, walaupun tanggal pengerjaannya berbeda.
- **Warna & ketebalan garis = frekuensi kolaborasi**, dihitung dari jumlah task bersama untuk pasangan karyawan tersebut.
- **Bar scale** menunjukkan rentang frekuensi kolaborasi dari paling sedikit ke paling banyak pada scope aktif.
- Toggle **Interactive** mengaktifkan atau mematikan overlay impuls neuron. Default **OFF** untuk menjaga performa.
- Saat **Interactive ON**, streak impuls dibuat lebih bercahaya; hover/klik node memperkuat glow dan kecepatan pada seluruh relasi node tersebut.
- Pada graph yang sangat padat, ambient impulse memprioritaskan relasi kolaborasi terkuat; relasi node yang sedang difokuskan tetap dianimasikan seluruhnya.
- **Hover garis** untuk melihat task, project, dan total jam yang menjadi dasar relasi.
- **Ukuran node** dapat diganti dari sidebar.
- Animasi adalah bantuan visual untuk menonjolkan pola relasi; warna node tetap menunjukkan community/cluster dan bukan penilaian performa individu.
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
