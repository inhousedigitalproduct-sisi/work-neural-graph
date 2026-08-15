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
DEFAULT_FUZZY_THRESHOLD = 0.90


def dataset_signature(dataframe: pd.DataFrame) -> tuple:
    if dataframe.empty:
        return (0,)
    return (
        len(dataframe),
        str(pd.to_datetime(dataframe["work_date"], errors="coerce").min()),
        str(pd.to_datetime(dataframe["work_date"], errors="coerce").max()),
        round(float(pd.to_numeric(dataframe["hours"], errors="coerce").fillna(0).sum()), 4),
    )


def build_deterministic_audit(dataframe: pd.DataFrame) -> dict[str, object]:
    prepared = prepare_quality_dataframe(dataframe)
    duration = find_duration_issues(prepared)
    copies = find_copy_pairs(prepared, DEFAULT_FUZZY_THRESHOLD)
    overlaps = find_overlap_pairs(prepared)
    kpis, entries, repeated, _ = managerial_summary(prepared, copies, overlaps, duration)
    return {
        "filtered": prepared,
        "kpis": kpis,
        "entries": entries,
        "copies": copies,
        "overlaps": overlaps,
        "duration": duration,
        "repeated": repeated,
        "dataset_signature": dataset_signature(dataframe),
        "fuzzy_threshold": DEFAULT_FUZZY_THRESHOLD,
    }


def pair_filter(dataframe: pd.DataFrame, row_ids: set[int]) -> pd.DataFrame:
    if dataframe.empty:
        return dataframe.copy()
    if "Row 1" not in dataframe.columns or "Row 2" not in dataframe.columns:
        return dataframe.copy()
    return dataframe[
        dataframe["Row 1"].isin(row_ids) & dataframe["Row 2"].isin(row_ids)
    ].reset_index(drop=True)


def semantic_signature(row_ids: set[int], semantic_threshold: float) -> tuple:
    return (
        tuple(sorted(row_ids)),
        round(float(semantic_threshold), 4),
        config.embedding_model,
    )


st.title("Audit Kualitas Timesheet")
st.caption(
    "Audit deterministic dijalankan saat dataset divalidasi di halaman Load Data. "
    "Halaman ini digunakan untuk membaca hasil dan evidence pada filter aktif."
)

source_dataframe = dataset_service.load_active_dataset()
if source_dataframe.empty:
    st.info("Belum ada dataset aktif. Unggah file timesheet melalui halaman Load Data.")
    st.stop()

active_signature = dataset_signature(source_dataframe)
result = st.session_state.get("quality_audit_result")
if result is None or result.get("dataset_signature") != active_signature:
    with st.spinner("Menyiapkan hasil audit dataset aktif…"):
        result = build_deterministic_audit(source_dataframe)
        st.session_state["quality_audit_result"] = result
        st.session_state.pop("quality_semantic_result", None)

filters, _ = render_shared_filters(source_dataframe)
with st.sidebar:
    st.divider()
    st.subheader("Analisis semantik")
    semantic_threshold = st.slider("Ambang relasi semantik", 0.60, 0.95, 0.82, 0.01)
    st.caption(f"Embedding: {config.embedding_provider.upper()} / {config.embedding_model}")
    st.caption(f"Near-copy audit menggunakan threshold tetap {DEFAULT_FUZZY_THRESHOLD:.2f} saat validasi dataset.")

prepared_full = result["filtered"]
filtered = apply_graph_filters(prepared_full, filters)
if filtered.empty:
    st.info("Filter saat ini tidak menghasilkan entri untuk dianalisis.")
    st.stop()

row_ids = set(filtered["row_id"].astype(int).tolist())
copies = pair_filter(result["copies"], row_ids)
overlaps = pair_filter(result["overlaps"], row_ids)
duration = result["duration"]
if not duration.empty:
    duration = duration[duration["row_id"].isin(row_ids)].reset_index(drop=True)

kpis, entry_scores, repeated, _ = managerial_summary(filtered, copies, overlaps, duration)

st.subheader("Ringkasan audit")
a, b, c, d = st.columns(4)
a.metric("Indikasi copy-paste", f"{kpis['copy']} / {kpis['total']}", f"{kpis['copy_rate']}%")
b.metric("Kualitas penulisan", f"{kpis['writing']} / 100")
c.metric("Entri overlap", kpis["overlap"])
d.metric("Indikator efektivitas", f"{kpis['effectiveness']} / 100")
st.caption(
    f"{kpis['minimal']} entri ({kpis['minimal_rate']}%) memiliki Note minim; "
    f"{kpis['duration']} entri memerlukan validasi durasi. "
    "Near-copy dihitung sekali saat validasi dataset; filter hanya menyaring hasil audit yang sudah tersedia."
)

entries_tab, copy_tab, overlap_tab, duration_tab, repeated_tab = st.tabs([
    "Kualitas Note", "Copy / Near-copy", "Overlap", "Durasi", "Aktivitas Berulang"
])
with entries_tab:
    st.dataframe(entry_scores, use_container_width=True, hide_index=True)
with copy_tab:
    if copies.empty:
        st.success("Tidak ada exact-copy atau near-copy pada scope aktif.")
    else:
        st.dataframe(copies, use_container_width=True, hide_index=True)
with overlap_tab:
    if overlaps.empty:
        st.success("Tidak ada overlap waktu yang terdeteksi pada scope aktif.")
    else:
        st.dataframe(overlaps, use_container_width=True, hide_index=True)
with duration_tab:
    if duration.empty:
        st.success("Tidak ada masalah konsistensi durasi yang terdeteksi pada scope aktif.")
    else:
        st.dataframe(duration, use_container_width=True, hide_index=True)
with repeated_tab:
    if repeated.empty:
        st.info("Tidak ada aktivitas berulang pada scope aktif.")
    else:
        st.dataframe(repeated, use_container_width=True, hide_index=True)

st.divider()
st.subheader("Analisis Semantik & Topic Grouping")
st.caption("Proses embedding tetap on-demand dan tidak ikut memperlambat validasi dataset utama.")
semantic_sig = semantic_signature(row_ids, semantic_threshold)

if st.button("Jalankan analisis semantik", type="secondary"):
    with st.status("Membuat embedding dan menghitung relasi semantik…", expanded=True) as status:
        progress = st.progress(0.0, text="Menyiapkan embedding")
        try:
            vectors = embed_texts(
                filtered["analysis_text"].tolist(),
                config.ollama_host,
                config.embedding_model,
                lambda done, total: progress.progress(
                    done / total if total else 1,
                    text=f"Embedding: {done:,}/{total:,}",
                ),
            )
            raw = semantic_pairs(vectors, filtered["row_id"].tolist(), semantic_threshold)
            semantic = enrich_semantic_pairs(raw, filtered)
            topic_data = filtered.copy()
            topic_data["Topic Group"] = cluster_vectors(vectors, semantic_threshold)
            topics = build_topic_summary(topic_data)
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
    st.info("Analisis semantik belum dijalankan untuk scope ini.")
elif semantic_result.get("signature") != semantic_sig:
    st.info("Ambang semantik atau scope berubah. Jalankan analisis semantik kembali bila dibutuhkan.")
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
