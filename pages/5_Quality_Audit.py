from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
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


ISSUE_METRICS = [
    ("copy_rate", "Copy / Near-copy"),
    ("exact_copy_rate", "Exact Copy"),
    ("minimal_note_rate", "Note Minim"),
    ("overlap_rate", "Overlap"),
    ("duration_issue_rate", "Duration Issue"),
    ("repeated_long_rate", "Repeated & Long"),
]


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


def affected_pair_ids(dataframe: pd.DataFrame) -> set[int]:
    if dataframe.empty or "Row 1" not in dataframe.columns or "Row 2" not in dataframe.columns:
        return set()
    return set(dataframe["Row 1"].astype(int).tolist()) | set(dataframe["Row 2"].astype(int).tolist())


@st.cache_data(show_spinner=False)
def build_quality_trend(dataframe: pd.DataFrame, grouping: str) -> pd.DataFrame:
    """Recalculate deterministic quality metrics per time bucket for comparable historical trends."""
    if dataframe.empty:
        return pd.DataFrame()

    source = dataframe.copy()
    source["work_date"] = pd.to_datetime(source["work_date"], errors="coerce")
    source = source[source["work_date"].notna()].copy()
    if source.empty:
        return pd.DataFrame()

    frequency = "M" if grouping == "Monthly" else "W-SUN"
    source["period_start"] = source["work_date"].dt.to_period(frequency).dt.start_time
    rows: list[dict[str, object]] = []

    for period_start, period_data in source.groupby("period_start", sort=True):
        prepared = prepare_quality_dataframe(period_data.drop(columns=["period_start"], errors="ignore"))
        duration = find_duration_issues(prepared)
        copies = find_copy_pairs(prepared, DEFAULT_FUZZY_THRESHOLD)
        overlaps = find_overlap_pairs(prepared)
        kpis, entries, repeated, _ = managerial_summary(prepared, copies, overlaps, duration)

        total = max(int(kpis["total"]), 1)
        exact_pairs = copies[copies["Jenis"] == "Exact copy"] if not copies.empty and "Jenis" in copies.columns else pd.DataFrame()
        exact_rate = len(affected_pair_ids(exact_pairs)) / total * 100
        overlap_rate = float(kpis["overlap"]) / total * 100
        duration_rate = float(kpis["duration"]) / total * 100
        repeated_long_rate = (
            float(entries["Berulang dan lama"].mean()) * 100
            if not entries.empty and "Berulang dan lama" in entries.columns
            else 0.0
        )

        rows.append(
            {
                "period_start": pd.Timestamp(period_start),
                "entries": int(kpis["total"]),
                "copy_rate": float(kpis["copy_rate"]),
                "exact_copy_rate": round(exact_rate, 1),
                "minimal_note_rate": float(kpis["minimal_rate"]),
                "writing_quality": float(kpis["writing"]),
                "overlap_rate": round(overlap_rate, 1),
                "duration_issue_rate": round(duration_rate, 1),
                "repeated_long_rate": round(repeated_long_rate, 1),
                "effectiveness": float(kpis["effectiveness"]),
                "repeated_groups": int(len(repeated)),
            }
        )

    return pd.DataFrame(rows).sort_values("period_start").reset_index(drop=True)


def build_score_trend_figure(trend: pd.DataFrame) -> go.Figure:
    figure = go.Figure()
    figure.add_trace(go.Scatter(
        x=trend["period_start"],
        y=trend["effectiveness"],
        mode="lines+markers",
        name="Overall Quality",
        line={"width": 4},
        marker={"size": 9},
        fill="tozeroy",
        fillcolor="rgba(148,163,184,0.08)",
        hovertemplate="%{x|%d %b %Y}<br>Overall Quality: %{y:.1f}<extra></extra>",
    ))
    figure.add_trace(go.Scatter(
        x=trend["period_start"],
        y=trend["writing_quality"],
        mode="lines+markers",
        name="Writing Quality",
        line={"width": 2, "dash": "dot"},
        marker={"size": 7},
        hovertemplate="%{x|%d %b %Y}<br>Writing Quality: %{y:.1f}<extra></extra>",
    ))
    figure.update_layout(
        height=390,
        margin={"l": 20, "r": 20, "t": 20, "b": 20},
        xaxis_title="Periode",
        yaxis_title="Score (0–100)",
        yaxis={"range": [0, 105]},
        hovermode="x unified",
        legend={"orientation": "h", "y": 1.08},
    )
    return figure


def build_issue_heatmap(trend: pd.DataFrame) -> go.Figure:
    labels = [label for _, label in ISSUE_METRICS]
    values = [[float(value) for value in trend[column].tolist()] for column, _ in ISSUE_METRICS]
    text = [[f"{value:.1f}%" for value in row] for row in values]
    figure = go.Figure(go.Heatmap(
        z=values,
        x=trend["period_start"],
        y=labels,
        text=text,
        texttemplate="%{text}",
        hovertemplate="%{y}<br>%{x|%d %b %Y}<br>%{z:.1f}%<extra></extra>",
        colorbar={"title": "Issue rate %"},
        colorscale="YlOrRd",
        zmin=0,
    ))
    figure.update_layout(
        height=390,
        margin={"l": 20, "r": 20, "t": 10, "b": 20},
        xaxis_title="Periode",
        yaxis_title="",
    )
    return figure


def build_issue_focus_figure(trend: pd.DataFrame, column: str, label: str) -> go.Figure:
    figure = go.Figure(go.Scatter(
        x=trend["period_start"],
        y=trend[column],
        mode="lines+markers",
        line={"width": 3},
        marker={"size": 9},
        fill="tozeroy",
        fillcolor="rgba(148,163,184,0.08)",
        hovertemplate=f"%{{x|%d %b %Y}}<br>{label}: %{{y:.1f}}%<extra></extra>",
    ))
    figure.update_layout(
        height=300,
        margin={"l": 20, "r": 20, "t": 10, "b": 20},
        xaxis_title="Periode",
        yaxis_title=f"{label} (%)",
        hovermode="x",
    )
    return figure


def metric_delta(trend: pd.DataFrame, column: str) -> float | None:
    if len(trend) < 2:
        return None
    return round(float(trend.iloc[-1][column]) - float(trend.iloc[-2][column]), 1)


st.title("Audit Kualitas Timesheet")
st.caption(
    "Audit deterministic dijalankan saat dataset divalidasi. Gunakan Current Snapshot untuk evidence saat ini "
    "dan Trend Analysis untuk mengevaluasi perubahan kualitas dari waktu ke waktu."
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

snapshot_tab, trend_tab = st.tabs(["Current Snapshot", "Trend Analysis"])

with snapshot_tab:
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

with trend_tab:
    st.subheader("Quality Trend")
    st.caption(
        "Setiap periode dihitung ulang dari data timesheet agar rate comparable. "
        "Gunakan arah metric di bawah agar kenaikan/penurunan tidak salah dibaca."
    )
    st.info(
        "↑ **High is better** = semakin tinggi nilainya semakin baik (Overall Quality, Writing Quality).  "
        "↓ **Low is better** = semakin rendah nilainya semakin baik (seluruh issue rate)."
    )
    grouping = st.segmented_control(
        "Grouping",
        options=["Monthly", "Weekly"],
        default="Monthly",
        key="quality_trend_grouping",
    ) or "Monthly"

    with st.spinner("Menghitung trend audit deterministic…"):
        trend = build_quality_trend(filtered, grouping)

    if trend.empty:
        st.info("Belum ada data yang cukup untuk membentuk trend pada scope aktif.")
    else:
        latest = trend.iloc[-1]
        k1, k2, k3, k4 = st.columns(4)
        with k1:
            st.metric(
                "Overall Quality",
                f"{float(latest['effectiveness']):.1f}",
                metric_delta(trend, "effectiveness"),
            )
            st.caption("↑ High is better")
        with k2:
            st.metric(
                "Copy / Near-copy",
                f"{float(latest['copy_rate']):.1f}%",
                metric_delta(trend, "copy_rate"),
                delta_color="inverse",
            )
            st.caption("↓ Low is better")
        with k3:
            st.metric(
                "Note Minim",
                f"{float(latest['minimal_note_rate']):.1f}%",
                metric_delta(trend, "minimal_note_rate"),
                delta_color="inverse",
            )
            st.caption("↓ Low is better")
        with k4:
            st.metric(
                "Writing Quality",
                f"{float(latest['writing_quality']):.1f}",
                metric_delta(trend, "writing_quality"),
            )
            st.caption("↑ High is better")

        st.markdown("#### Overall Quality Trend")
        st.caption(
            "↑ **High is better** — garis utama menunjukkan Overall Quality dan garis putus-putus menunjukkan Writing Quality. "
            "Kenaikan score berarti kualitas membaik."
        )
        st.plotly_chart(build_score_trend_figure(trend), use_container_width=True)

        st.markdown("#### Issue Trend Heatmap")
        st.caption(
            "↓ **Low is better** — warna yang lebih kuat menunjukkan issue rate lebih tinggi. "
            "Nilai yang turun dari periode ke periode berarti kondisi membaik."
        )
        st.plotly_chart(build_issue_heatmap(trend), use_container_width=True)

        metric_options = {label: column for column, label in ISSUE_METRICS}
        focused_label = st.selectbox(
            "Lihat trend issue secara detail",
            options=list(metric_options),
            key="quality_trend_focus_metric",
        )
        focused_column = metric_options[focused_label]
        focus_delta = metric_delta(trend, focused_column)
        direction = "stabil" if focus_delta in (None, 0) else "menurun" if focus_delta < 0 else "meningkat"
        interpretation = (
            "Belum ada periode pembanding."
            if focus_delta is None
            else "Improving" if focus_delta < 0
            else "Stable" if focus_delta == 0
            else "Needs attention"
        )
        st.caption(
            f"↓ **Low is better** — periode terbaru: **{float(latest[focused_column]):.1f}%**. "
            f"Dibanding periode sebelumnya: **{direction}**"
            + ("." if focus_delta is None else f" ({focus_delta:+.1f} pp) · **{interpretation}**.")
        )
        st.plotly_chart(build_issue_focus_figure(trend, focused_column, focused_label), use_container_width=True)

        with st.expander("Data trend lengkap", expanded=False):
            trend_view = trend.rename(columns={
                "period_start": "Periode",
                "entries": "Entri",
                "copy_rate": "Copy/Near-copy (%)",
                "exact_copy_rate": "Exact Copy (%)",
                "minimal_note_rate": "Note Minim (%)",
                "writing_quality": "Writing Quality",
                "overlap_rate": "Overlap (%)",
                "duration_issue_rate": "Duration Issue (%)",
                "repeated_long_rate": "Repeated & Long (%)",
                "effectiveness": "Overall Quality",
                "repeated_groups": "Repeated Groups",
            })
            st.dataframe(trend_view, use_container_width=True, hide_index=True)

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
