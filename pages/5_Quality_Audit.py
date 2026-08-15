from __future__ import annotations

import pandas as pd
import streamlit as st

from src.graph.builder import apply_graph_filters
from src.quality.timesheet_quality import (
    build_topic_summary,
    cluster_vectors,
    embed_texts,
    enrich_semantic_pairs,
    find_copy_pairs,
    find_duration_issues,
    find_overlap_pairs,
    managerial_summary,
    prepare_quality_dataframe,
    semantic_pairs,
)
from src.services import TimesheetDataService
from src.ui.components import render_shared_filters
from src.utils.config import get_config

config = get_config()
dataset_service = TimesheetDataService(config.db_path)


def deterministic_signature(filters, fuzzy_threshold: float) -> tuple:
    return (
        filters.start_date,
        filters.end_date,
        tuple(filters.employee_names),
        tuple(filters.projects),
        tuple(filters.task_keys),
        tuple(filters.states),
        filters.note_keyword,
        round(float(fuzzy_threshold), 4),
    )


def semantic_signature(base_signature: tuple, semantic_threshold: float) -> tuple:
    return (*base_signature, round(float(semantic_threshold), 4), config.embedding_model)


st.title("Audit Kualitas Timesheet")
st.caption("Audit Python ditampilkan lebih dulu. Analisis semantik dan topic grouping dijalankan terpisah hanya saat dibutuhkan.")

source_dataframe = dataset_service.load_active_dataset()
if source_dataframe.empty:
    st.info("Belum ada dataset aktif. Unggah file timesheet melalui halaman Load Data.")
    st.stop()

filters, _ = render_shared_filters(source_dataframe)
with st.sidebar:
    st.divider()
    st.subheader("Pengaturan audit")
    fuzzy_threshold = st.slider("Ambang near-copy", 0.70, 1.00, 0.90, 0.01)
    semantic_threshold = st.slider("Ambang relasi semantik", 0.60, 0.95, 0.82, 0.01)
    st.caption(f"Embedding: {config.embedding_provider.upper()} / {config.embedding_model}")

current_signature = deterministic_signature(filters, fuzzy_threshold)

if st.button("Jalankan audit kualitas", type="primary"):
    filtered = prepare_quality_dataframe(apply_graph_filters(source_dataframe, filters))
    if filtered.empty:
        st.warning("Filter saat ini tidak menghasilkan entri untuk dianalisis.")
        st.stop()

    with st.status("Menjalankan audit Python…", expanded=True) as status:
        activity = st.empty()
        progress = st.progress(0.0, text="Menyiapkan audit")
        activity.info("1/3 — Validasi durasi dan waktu kerja")
        duration = find_duration_issues(filtered)
        progress.progress(0.20, text="Validasi durasi selesai")

        activity.info("2/3 — Deteksi exact copy dan near-copy")
        copies = find_copy_pairs(
            filtered,
            fuzzy_threshold,
            lambda done, total: progress.progress(0.20 + 0.55 * (done / total if total else 1), text=f"Fuzzy matching: {done:,}/{total:,}"),
        )

        activity.info("3/3 — Overlap, kualitas tulisan, dan aktivitas berulang")
        overlaps = find_overlap_pairs(filtered)
        kpis, entry_scores, repeated, _ = managerial_summary(filtered, copies, overlaps, duration)
        progress.progress(1.0, text="Audit Python selesai")
        status.update(label="Audit Python selesai", state="complete", expanded=False)

    st.session_state["quality_audit_result"] = {
        "filtered": filtered,
        "kpis": kpis,
        "entries": entry_scores,
        "copies": copies,
        "overlaps": overlaps,
        "duration": duration,
        "repeated": repeated,
        "signature": current_signature,
    }
    st.session_state.pop("quality_semantic_result", None)

result = st.session_state.get("quality_audit_result")
if result is None:
    st.info("Pilih filter lalu tekan **Jalankan audit kualitas**. Analisis semantik tidak akan memperlambat proses awal.")
    st.stop()
if result.get("signature") != current_signature:
    st.info("Filter atau ambang near-copy berubah. Jalankan audit kualitas kembali agar hasil mengikuti scope aktif.")
    st.stop()

kpis = result["kpis"]
st.subheader("Ringkasan audit")
a, b, c, d = st.columns(4)
a.metric("Indikasi copy-paste", f"{kpis['copy']} / {kpis['total']}", f"{kpis['copy_rate']}%")
b.metric("Kualitas penulisan", f"{kpis['writing']} / 100")
c.metric("Entri overlap", kpis["overlap"])
d.metric("Indikator efektivitas", f"{kpis['effectiveness']} / 100")
st.caption(
    f"{kpis['minimal']} entri ({kpis['minimal_rate']}%) memiliki Note minim; "
    f"{kpis['duration']} entri memerlukan validasi durasi. Semua angka di atas dihitung Python secara deterministik."
)

entries_tab, copy_tab, overlap_tab, duration_tab, repeated_tab = st.tabs([
    "Kualitas Note", "Copy / Near-copy", "Overlap", "Durasi", "Aktivitas Berulang"
])
with entries_tab:
    st.dataframe(result["entries"], use_container_width=True, hide_index=True)
with copy_tab:
    if result["copies"].empty:
        st.success("Tidak ada exact-copy atau near-copy pada ambang aktif.")
    else:
        st.dataframe(result["copies"], use_container_width=True, hide_index=True)
with overlap_tab:
    if result["overlaps"].empty:
        st.success("Tidak ada overlap waktu yang terdeteksi.")
    else:
        st.dataframe(result["overlaps"], use_container_width=True, hide_index=True)
with duration_tab:
    if result["duration"].empty:
        st.success("Tidak ada masalah konsistensi durasi yang terdeteksi.")
    else:
        st.dataframe(result["duration"], use_container_width=True, hide_index=True)
with repeated_tab:
    if result["repeated"].empty:
        st.info("Tidak ada aktivitas berulang pada scope aktif.")
    else:
        st.dataframe(result["repeated"], use_container_width=True, hide_index=True)

st.divider()
st.subheader("Analisis Semantik & Topic Grouping")
st.caption("Proses ini terpisah dari audit utama karena membutuhkan embedding. Jalankan hanya saat Anda ingin melihat kedekatan makna dan kelompok topik.")
semantic_sig = semantic_signature(current_signature, semantic_threshold)

if st.button("Jalankan analisis semantik", type="secondary"):
    filtered = result["filtered"].copy()
    with st.status("Membuat embedding dan menghitung relasi semantik…", expanded=True) as status:
        progress = st.progress(0.0, text="Menyiapkan embedding")
        try:
            vectors = embed_texts(
                filtered["analysis_text"].tolist(),
                config.ollama_host,
                config.embedding_model,
                lambda done, total: progress.progress(done / total if total else 1, text=f"Embedding: {done:,}/{total:,}"),
            )
            raw = semantic_pairs(vectors, filtered["row_id"].tolist(), semantic_threshold)
            semantic = enrich_semantic_pairs(raw, filtered)
            filtered["Topic Group"] = cluster_vectors(vectors, semantic_threshold)
            topics = build_topic_summary(filtered)
            st.session_state["quality_semantic_result"] = {
                "semantic": semantic,
                "topics": topics,
                "signature": semantic_sig,
                "error": None,
            }
            progress.progress(1.0, text="Analisis semantik selesai")
            status.update(label="Analisis semantik selesai", state="complete", expanded=False)
        except Exception as exc:
            st.session_state["quality_semantic_result"] = {
                "semantic": pd.DataFrame(),
                "topics": pd.DataFrame(),
                "signature": semantic_sig,
                "error": str(exc),
            }
            status.update(label="Analisis semantik gagal", state="error", expanded=False)

semantic_result = st.session_state.get("quality_semantic_result")
if semantic_result is None:
    st.info("Analisis semantik belum dijalankan untuk hasil audit ini.")
elif semantic_result.get("signature") != semantic_sig:
    st.info("Ambang semantik atau scope berubah. Jalankan analisis semantik kembali.")
elif semantic_result.get("error"):
    st.warning("Analisis semantik tidak tersedia: " + semantic_result["error"])
else:
    semantic_tab, topic_tab = st.tabs(["Semantic Similarity", "Topic Grouping"])
    with semantic_tab:
        if semantic_result["semantic"].empty:
            st.info("Tidak ada pasangan yang melewati ambang semantic similarity aktif.")
        else:
            st.dataframe(semantic_result["semantic"], use_container_width=True, hide_index=True)
    with topic_tab:
        st.dataframe(semantic_result["topics"], use_container_width=True, hide_index=True)
