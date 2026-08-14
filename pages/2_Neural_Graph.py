from __future__ import annotations

import logging

import pandas as pd
import streamlit as st

from src.analytics.service import AnalyticsService
from src.domain.models import GraphStrategy
from src.graph.visualizer import build_graph_figure
from src.llm.client import LLMError
from src.llm.service import create_ai_analyst_service
from src.services import GraphService, TimesheetDataService
from src.ui.components import (
    render_analytics_summary,
    render_graph_summary,
    render_llm_provider_selector,
    render_shared_filters,
)
from src.utils.config import get_config

logger = logging.getLogger(__name__)

config = get_config()
service = GraphService(config.db_path)
analytics_service = AnalyticsService(config.db_path)
dataset_service = TimesheetDataService(config.db_path)


def build_graph_llm_brief(graph_result, analytics_snapshot) -> dict:
    nodes = graph_result.node_dataframe.sort_values(["degree", "total_hours"], ascending=False).head(5).copy()
    nodes["date"] = pd.to_datetime(nodes["date"]).dt.date.astype(str)
    nodes["total_hours"] = nodes["total_hours"].round(2)
    edges = graph_result.edge_dataframe.sort_values(["interruption_days", "related_hours"], ascending=False).head(5).copy()
    if not edges.empty:
        edges["source"] = pd.to_datetime(edges["source"]).dt.date.astype(str)
        edges["target"] = pd.to_datetime(edges["target"]).dt.date.astype(str)
        edges["related_hours"] = edges["related_hours"].round(2)
    return {
        "graph_summary": {
            "nodes": graph_result.summary.nodes,
            "edges": graph_result.summary.edges,
            "active_days": graph_result.summary.active_days,
            "unique_tasks": graph_result.summary.unique_tasks,
            "total_hours": round(graph_result.summary.total_hours, 2),
            "average_degree": round(graph_result.summary.average_degree, 2),
            "connected_components": graph_result.summary.connected_components,
            "density": round(graph_result.summary.density, 4),
        },
        "work_pattern_kpi": {
            "fragmented_tasks": analytics_snapshot.kpi.fragmented_tasks,
            "interrupted_tasks": analytics_snapshot.kpi.interrupted_tasks,
            "average_continuity_ratio": round(analytics_snapshot.kpi.average_continuity_ratio, 3),
            "average_context_switches": round(analytics_snapshot.kpi.average_context_switches, 2),
        },
        "most_connected_dates": nodes.to_dict(orient="records"),
        "longest_relationship_gaps": edges.to_dict(orient="records"),
        "interpretation_guidance": {
            "audience": "manager / management",
            "focus": [
                "kesinambungan pekerjaan lintas tanggal",
                "tanggal yang menjadi titik konsentrasi aktivitas",
                "relasi dengan jeda panjang yang perlu diverifikasi",
                "pertanyaan yang perlu dibahas manajemen tanpa menilai individu",
            ],
        },
    }


st.title("Neural Graph")
st.caption("Peta kesinambungan pekerjaan antar tanggal dari data timesheet yang sedang difilter.")

source_dataframe = dataset_service.load_active_dataset()
if source_dataframe.empty:
    st.info("No timesheet data is available. Load data from the Load Data page.")
    st.stop()

source_dataframe["work_date"] = pd.to_datetime(source_dataframe["work_date"])

filters, selected_strategy = render_shared_filters(source_dataframe, include_strategy=True)
selected_provider = render_llm_provider_selector(config)
selected_profile = config.llm_profile(selected_provider) if selected_provider != "off" else None
ai_service = None
llm_status = None
if selected_profile is not None:
    ai_service = create_ai_analyst_service(
        db_path=config.db_path,
        provider=selected_profile.provider,
        model=selected_profile.model,
        timeout_seconds=config.llm_timeout_seconds,
        api_key_env=selected_profile.api_key_env or config.openai_api_key_env,
        ollama_host=selected_profile.host or config.ollama_host,
    )
    llm_status = ai_service.get_status()

with st.sidebar:
    st.divider()
    with st.expander("Graph Settings", expanded=True):
        node_size_metric = st.selectbox(
            "Node Size Metric",
            ["total_hours", "unique_tasks", "unique_employees", "unique_projects", "degree"],
            index=0,
            key="neural_graph_node_size_metric",
        )
        edge_width_metric = st.selectbox(
            "Edge Weight Metric",
            ["task_count", "related_hours", "gap_days", "interruption_days"],
            index=0,
            key="neural_graph_edge_width_metric",
        )
result = service.build_graph(filters=filters, strategy=selected_strategy or GraphStrategy.SEQUENTIAL)
analytics_snapshot = analytics_service.build_snapshot(
    filters=filters,
    strategy=selected_strategy or GraphStrategy.SEQUENTIAL,
)

render_graph_summary(
    nodes=result.summary.nodes,
    edges=result.summary.edges,
    active_days=result.summary.active_days,
    unique_tasks=result.summary.unique_tasks,
    total_hours=result.summary.total_hours,
    average_degree=result.summary.average_degree,
)
with st.expander("Cara membaca grafik", expanded=True):
    left, middle, right = st.columns(3)
    left.markdown("**Lingkaran = satu tanggal kerja**  \nUkuran lingkaran mengikuti metrik *Node Size Metric* di sidebar.")
    middle.markdown("**Garis = task yang muncul lagi**  \nSebuah garis berarti minimal satu task dikerjakan pada kedua tanggal tersebut.")
    right.markdown("**Ukuran & warna = nilai metrik node**  \nSemakin besar/gelap node, semakin tinggi nilai metrik yang dipilih.")
    st.info(
        "Penting: posisi node hanya menunjukkan struktur hubungan antar tanggal dari layout jaringan. "
        "Posisi vertikal/horizontal node **bukan sumbu jumlah jam** dan tidak boleh dibandingkan dengan posisi angka pada legenda warna. "
        "Mulailah dengan memilih satu pegawai atau satu proyek. Arahkan kursor ke lingkaran untuk melihat tanggal lengkap, "
        "aktivitas, pegawai, proyek, Note, dan tanggal lain yang terhubung. Arahkan kursor ke titik tengah garis untuk melihat "
        "task yang menjadi alasan relasi. 'Relasi tanggal' adalah jumlah tanggal lain yang terhubung, bukan jumlah task. "
        "Pada strategi Sequential, satu task hanya menghubungkan dua kemunculan tanggal yang berurutan untuk task tersebut."
    )
st.subheader("Period Analysis")
render_analytics_summary(
    total_hours=analytics_snapshot.kpi.total_hours,
    active_days=analytics_snapshot.kpi.active_days,
    unique_tasks=analytics_snapshot.kpi.unique_tasks,
    unique_employees=analytics_snapshot.kpi.unique_employees,
    unique_projects=analytics_snapshot.kpi.unique_projects,
    fragmented_tasks=analytics_snapshot.kpi.fragmented_tasks,
    interrupted_tasks=analytics_snapshot.kpi.interrupted_tasks,
    average_context_switches=analytics_snapshot.kpi.average_context_switches,
    average_continuity_ratio=analytics_snapshot.kpi.average_continuity_ratio,
)

if result.filtered_dataframe.empty:
    st.info("The selected filters returned no rows.")
    st.stop()

label_mode_options = ["Auto", "All", "None"]
auto_label_mode = "None" if result.summary.nodes > 50 else "All"

with st.sidebar:
    with st.expander("Display Density", expanded=True):
        label_mode = st.selectbox(
            "Date Labels",
            label_mode_options,
            index=label_mode_options.index("Auto"),
            key="neural_graph_label_mode",
            help="Auto hides labels on dense graphs to preserve readability.",
        )
        min_edge_task_count = 1
        if not result.edge_dataframe.empty:
            edge_task_min = int(result.edge_dataframe["task_count"].min())
            edge_task_max = int(result.edge_dataframe["task_count"].max())
            min_edge_task_count = st.slider(
                "Minimum Shared Task Count",
                min_value=edge_task_min,
                max_value=edge_task_max,
                value=edge_task_min,
                key="neural_graph_min_edge_task_count",
                help="Display only edges meeting this shared-task threshold.",
            )

effective_label_mode = auto_label_mode if label_mode == "Auto" else label_mode
display_edge_dataframe = result.edge_dataframe.copy()
if not display_edge_dataframe.empty:
    display_edge_dataframe = display_edge_dataframe[
        display_edge_dataframe["task_count"] >= min_edge_task_count
    ].reset_index(drop=True)

if result.summary.edges == 0:
    st.info("No cross-date task relationships were found for the selected filters.")
    if result.summary.nodes > 0:
        st.dataframe(result.node_dataframe, use_container_width=True)
    st.stop()

if display_edge_dataframe.empty:
    st.info("The current edge threshold hides all relationships. Lower the threshold to display connections.")

if label_mode == "Auto" and auto_label_mode == "None":
    st.warning(
        f"Dense graph detected: {result.summary.nodes} nodes and {result.summary.edges} edges. "
        "Date labels are hidden automatically."
    )
elif result.summary.nodes > 300 or result.summary.edges > 2000:
    st.warning(
        f"Large graph detected: {result.summary.nodes} nodes and {result.summary.edges} edges. "
        "Interaction may slow down."
    )

if len(display_edge_dataframe) != len(result.edge_dataframe):
    st.caption(
        f"Displaying {len(display_edge_dataframe)} of {len(result.edge_dataframe)} edges after the shared-task filter."
    )

figure = build_graph_figure(
    result.graph,
    result.node_dataframe,
    display_edge_dataframe,
    node_size_metric=node_size_metric,
    edge_width_metric=edge_width_metric,
    show_node_labels=effective_label_mode == "All",
    activity_dataframe=result.filtered_dataframe,
)
st.subheader("Peta hubungan pekerjaan")
metric_display_labels = {
    "total_hours": "Total jam kerja",
    "unique_tasks": "Jumlah task",
    "unique_employees": "Jumlah pegawai",
    "unique_projects": "Jumlah proyek",
    "degree": "Jumlah relasi tanggal",
}
metric_display = metric_display_labels.get(node_size_metric, node_size_metric.replace("_", " ").title())
st.caption(
    f"Ukuran & warna node: **{metric_display}**. "
    f"Ketebalan garis: **{edge_width_metric.replace('_', ' ')}**. "
    "Legenda warna ditempatkan horizontal agar tidak terbaca sebagai sumbu Y."
)
st.info(
    "**Cara membaca posisi node:** posisi node hanya membantu memperlihatkan pola hubungan jaringan. "
    f"Untuk membaca **{metric_display.lower()}**, gunakan angka pada hover serta ukuran/warna node — bukan posisi node di area grafik."
)
st.plotly_chart(figure, use_container_width=True)

st.subheader("Interpretasi manajerial")
if selected_provider == "off":
    st.caption("AI Interpretation sedang Off. Grafik dan seluruh metrik Python tetap tersedia.")
else:
    provider_label = "OpenAI" if selected_provider == "openai" else "Qwen Local"
    model_label = llm_status.model if llm_status is not None else selected_profile.model
    st.caption(
        f"{provider_label} / {model_label} membaca fakta yang sudah dihitung Python lalu menyusunnya menjadi ringkasan eksekutif. "
        "Fokusnya adalah pola kerja, area perhatian, dan bahan diskusi manajemen—bukan penilaian performa individu."
    )

interpretation_available = (
    selected_provider != "off"
    and ai_service is not None
    and llm_status is not None
    and llm_status.available
)
button_label = "Buat interpretasi grafik"
if selected_provider == "openai":
    button_label += " dengan OpenAI"
elif selected_provider == "ollama":
    button_label += " dengan Qwen Local"

if st.button(button_label, disabled=not interpretation_available):
    model_label = llm_status.model
    with st.status(f"{model_label} sedang menafsirkan pola grafik…", expanded=True) as llm_progress:
        try:
            brief = build_graph_llm_brief(result, analytics_snapshot)
            explanation, duration, _ = ai_service.explain_result(
                question=(
                    "Buat interpretasi neural graph untuk level manajemen. Mulai dengan ringkasan eksekutif yang high-level, "
                    "lalu jelaskan sinyal utama yang benar-benar terlihat dari payload. Gunakan bagian perhatian untuk hal yang "
                    "perlu ditanggapi atau didiskusikan manajemen, dan bagian investigasi untuk pertanyaan verifikasi berikutnya. "
                    "Bedakan fakta dari hipotesis, jangan menilai performa individu, dan jangan membuat angka baru."
                ),
                result_payload=brief,
            )
            st.session_state["neural_graph_llm_result"] = {
                "explanation": explanation,
                "provider": selected_provider,
                "model": model_label,
            }
            st.session_state.pop("neural_graph_llm_error", None)
            llm_progress.update(
                label=f"Interpretasi {model_label} selesai ({duration:.1f} detik)",
                state="complete",
                expanded=False,
            )
        except (LLMError, ValueError) as exc:
            st.session_state["neural_graph_llm_error"] = str(exc)
            llm_progress.update(label="Interpretasi LLM tidak tersedia", state="error", expanded=False)

if st.session_state.get("neural_graph_llm_error"):
    st.warning("Interpretasi LLM tidak tersedia: " + st.session_state["neural_graph_llm_error"])
if st.session_state.get("neural_graph_llm_result"):
    llm_result = st.session_state["neural_graph_llm_result"]
    if llm_result.get("provider") == selected_provider:
        explanation = llm_result["explanation"]
        st.caption(f"Hasil interpretasi: {llm_result['model']}")
        st.write(explanation.summary)
        for heading, items in (
            ("Sinyal utama dari data", explanation.observations),
            ("Perlu tanggapan / diskusi manajemen", explanation.risks_or_attention_points),
            ("Pertanyaan untuk verifikasi lanjutan", explanation.recommended_investigation),
        ):
            if items:
                st.markdown(f"**{heading}**")
                for item in items:
                    st.write(f"- {item}")

with st.expander("Edge Details", expanded=False):
    edge_details = display_edge_dataframe.copy()
    if not edge_details.empty:
        edge_details["source"] = edge_details["source"].dt.date.astype(str)
        edge_details["target"] = edge_details["target"].dt.date.astype(str)
    st.dataframe(edge_details, use_container_width=True)

with st.expander("Node Details", expanded=False):
    node_details = result.node_dataframe.copy()
    if not node_details.empty:
        node_details["date"] = node_details["date"].dt.date.astype(str)
    st.dataframe(node_details, use_container_width=True)

with st.expander("Developer Details", expanded=False):
    st.caption(f"LLM selection: {selected_provider}")
    st.json(dataset_service.get_data_source_debug())
