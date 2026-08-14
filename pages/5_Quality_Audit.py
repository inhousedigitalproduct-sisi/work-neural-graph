from __future__ import annotations

import io

import pandas as pd
import streamlit as st

from src.llm.client import LLMError
from src.llm.service import create_ai_analyst_service
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
from src.ui.components import render_llm_provider_selector, render_shared_filters
from src.utils.config import get_config

config = get_config()
dataset_service = TimesheetDataService(config.db_path)


def audit_signature(
    filters,
    fuzzy_threshold: float,
    semantic_threshold: float,
    use_embeddings: bool,
    llm_provider: str,
) -> tuple:
    return (
        filters.start_date,
        filters.end_date,
        tuple(filters.employee_names),
        tuple(filters.projects),
        tuple(filters.task_keys),
        tuple(filters.states),
        filters.note_keyword,
        round(float(fuzzy_threshold), 4),
        round(float(semantic_threshold), 4),
        bool(use_embeddings),
        llm_provider,
    )


def build_quality_llm_brief(
    kpis: dict,
    entries: pd.DataFrame,
    copies: pd.DataFrame,
    overlaps: pd.DataFrame,
    repeated: pd.DataFrame,
    topics: pd.DataFrame,
) -> dict:
    category_counts = entries["Kategori"].value_counts().to_dict() if not entries.empty else {}
    copy_types = copies["Jenis"].value_counts().to_dict() if not copies.empty and "Jenis" in copies.columns else {}
    repeated_brief = repeated.head(5)[
        [
            column
            for column in ["Aktivitas", "Jumlah pengulangan", "Total jam", "Cenderung lama"]
            if column in repeated.columns
        ]
    ].to_dict(orient="records") if not repeated.empty else []
    topic_brief = topics.head(5)[
        [
            column
            for column in ["Tema representatif", "Jumlah entri", "Total jam"]
            if column in topics.columns
        ]
    ].to_dict(orient="records") if not topics.empty else []
    return {
        "scope_kpi": kpis,
        "writing_categories": category_counts,
        "copy_pair_count": int(len(copies)),
        "copy_pair_types": copy_types,
        "overlap_pair_count": int(len(overlaps)),
        "repeated_activity_examples": repeated_brief,
        "semantic_topic_examples": topic_brief,
        "interpretation_guidance": {
            "audience": "management",
            "goal": "prioritize policy/process discussion and validation, not employee performance judgement",
            "note": "all figures are deterministic Python outputs; do not invent new numbers",
        },
    }


def display_deterministic_recommendations(recommendations: list[str]) -> None:
    for number, recommendation in enumerate(recommendations, start=1):
        st.write(f"{number}. {recommendation}")


st.title("Audit Kualitas Timesheet")
st.caption(
    "Mengaudit kualitas pencatatan timesheet dari dataset aktif: copy/near-copy, kualitas Note, pengulangan, durasi, overlap, dan relasi semantik."
)

source_dataframe = dataset_service.load_active_dataset()
if source_dataframe.empty:
    st.info("Belum ada dataset aktif. Unggah file timesheet terlebih dahulu melalui halaman Load Data.")
    if st.button("Buka Load Data"):
        st.switch_page("pages/1_Load_Data.py")
    st.stop()

filters, _ = render_shared_filters(source_dataframe)
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
    st.subheader("Pengaturan audit")
    fuzzy_threshold = st.slider(
        "Ambang near-copy",
        0.70,
        1.00,
        0.90,
        0.01,
        help="Makin tinggi nilainya, makin mirip Note yang diperlukan untuk dianggap near-copy.",
    )
    semantic_threshold = st.slider(
        "Ambang relasi semantik",
        0.60,
        0.95,
        0.82,
        0.01,
        help="Makin tinggi nilainya, makin dekat makna dua entri yang diperlukan agar dihubungkan.",
    )
    use_embeddings = st.toggle(
        "Analisis relasi semantik",
        value=config.embedding_enabled,
        help="Menggunakan model embedding Ollama dan dapat membutuhkan waktu lebih lama.",
    )
    if selected_provider == "off":
        st.caption("LLM interpretasi: Off")
    elif llm_status is not None:
        st.caption(
            f"LLM interpretasi: {selected_provider.upper()} / {llm_status.model} "
            f"({'siap' if llm_status.available else 'offline'})"
        )
    st.caption(f"Model embedding: {config.embedding_provider.upper()} / {config.embedding_model}")
    with st.expander("Cara membaca hasil", expanded=False):
        st.markdown(
            "- **Copy/near-copy**: Note identik atau hampir sama milik pegawai yang sama; perlu verifikasi, bukan otomatis kesalahan.  \n"
            "- **Kualitas Note**: proxy kelengkapan aksi, objek, hasil, dan konteks.  \n"
            "- **Overlap**: dua rentang waktu milik pegawai yang sama saling bertumpang tindih; perlu konfirmasi konteks.  \n"
            "- **Relasi semantik**: dua entri bermakna dekat berdasarkan embedding; bukan bukti duplikasi.  \n"
            "- **Efektivitas**: proxy kualitas pencatatan, bukan nilai produktivitas atau kualitas hasil kerja."
        )

current_audit_signature = audit_signature(
    filters,
    fuzzy_threshold,
    semantic_threshold,
    use_embeddings,
    selected_provider,
)

if st.button("Jalankan audit kualitas", type="primary"):
    from src.graph.builder import apply_graph_filters

    filtered = prepare_quality_dataframe(apply_graph_filters(source_dataframe, filters))
    if filtered.empty:
        st.warning("Filter saat ini tidak menghasilkan entri untuk dianalisis.")
        st.stop()

    with st.status("Menjalankan audit kualitas…", expanded=True) as progress_status:
        activity = st.empty()
        progress = st.progress(0, text="Menyiapkan audit")

        activity.info("Tahap 1/6 — Memvalidasi durasi dan waktu kerja.")
        duration = find_duration_issues(filtered)

        activity.info("Tahap 2/6 — Mendeteksi exact copy dan near-copy pada Note.")
        copies = find_copy_pairs(
            filtered,
            fuzzy_threshold,
            lambda done, total: progress.progress(
                done / total if total else 1,
                text=f"Fuzzy matching: {done:,} / {total:,} pasangan",
            ),
        )

        activity.info("Tahap 3/6 — Memeriksa overlap waktu dan aktivitas berulang.")
        overlaps = find_overlap_pairs(filtered)
        kpis, entry_scores, repeated, deterministic_recommendations = managerial_summary(
            filtered,
            copies,
            overlaps,
            duration,
        )

        semantic_raw = pd.DataFrame()
        semantic = pd.DataFrame()
        topics = pd.DataFrame()
        embedding_error = None
        if use_embeddings:
            activity.info("Tahap 4/6 — Membuat embedding lokal, relasi semantik, dan kelompok topik.")
            try:
                vectors = embed_texts(
                    filtered["analysis_text"].tolist(),
                    config.ollama_host,
                    config.embedding_model,
                    lambda done, total: progress.progress(
                        done / total if total else 1,
                        text=f"Embedding: {done:,} / {total:,} entri",
                    ),
                )
                semantic_raw = semantic_pairs(vectors, filtered["row_id"].tolist(), semantic_threshold)
                semantic = enrich_semantic_pairs(semantic_raw, filtered)
                filtered["Topic Group"] = cluster_vectors(vectors, semantic_threshold)
                topics = build_topic_summary(filtered)
            except Exception as exc:  # Embedding/model failures must not hide deterministic results.
                embedding_error = str(exc)

        quality_llm = None
        llm_error = None
        activity.info("Tahap 5/6 — Menyusun rekomendasi high-level untuk manajemen.")
        if ai_service is not None and llm_status is not None and llm_status.available:
            try:
                brief = build_quality_llm_brief(kpis, entry_scores, copies, overlaps, repeated, topics)
                quality_llm, _duration, _ = ai_service.explain_result(
                    question=(
                        "Buat rekomendasi high-level untuk manajemen berdasarkan audit kualitas timesheet ini. "
                        "Ringkas implikasi proses/kebijakan, sebutkan hal yang perlu didiskusikan manajemen, dan berikan pertanyaan "
                        "investigasi lanjutan. Gunakan hanya fakta pada payload, jangan menciptakan angka, dan jangan menilai performa individu. "
                        "Prioritaskan perbaikan standar pencatatan, governance review, kategorisasi pekerjaan, dan validasi data yang paling relevan."
                    ),
                    result_payload=brief,
                )
            except (LLMError, ValueError) as exc:
                llm_error = str(exc)

        activity.info("Tahap 6/6 — Menyiapkan tabel bukti dan ringkasan akhir.")
        progress.progress(1.0, text="Audit selesai")
        progress_status.update(label="Audit kualitas selesai", state="complete", expanded=False)

    st.session_state["quality_audit_result"] = {
        "filtered": filtered,
        "kpis": kpis,
        "entries": entry_scores,
        "copies": copies,
        "overlaps": overlaps,
        "duration": duration,
        "repeated": repeated,
        "semantic": semantic,
        "semantic_raw": semantic_raw,
        "topics": topics,
        "recommendations": deterministic_recommendations,
        "quality_llm": quality_llm,
        "llm_error": llm_error,
        "embedding_error": embedding_error,
        "audit_signature": current_audit_signature,
        "llm_provider": selected_provider,
        "llm_model": llm_status.model if llm_status is not None else None,
    }

result = st.session_state.get("quality_audit_result")
if result is None:
    st.info("Pilih filter, pengaturan audit, dan LLM bila diperlukan, lalu tekan **Jalankan audit kualitas**.")
    st.stop()
if result.get("audit_signature") != current_audit_signature:
    st.info(
        "Filter, pengaturan audit, atau pilihan LLM berubah sejak proses terakhir. Jalankan audit kembali agar seluruh temuan dan rekomendasi mengikuti scope aktif."
    )
    st.stop()

kpis = result["kpis"]
st.subheader("Ringkasan manajerial")
a, b, c, d = st.columns(4)
a.metric(
    "Indikasi copy-paste",
    f"{kpis['copy']} / {kpis['total']}",
    f"{kpis['copy_rate']}%",
    help=(
        "Jumlah entri unik yang terlibat minimal satu pasangan exact-copy atau near-copy pada pegawai yang sama, dibanding total entri filter aktif. "
        "Ini adalah sinyal verifikasi kualitas Note, bukan otomatis kesalahan."
    ),
)
b.metric(
    "Kualitas penulisan",
    f"{kpis['writing']} / 100",
    help=(
        "Rata-rata skor heuristik kelengkapan Note: panjang penjelasan, keberadaan kata aksi/hasil, variasi informasi, dan konteks objek/modul. "
        "Skor ini mengukur kualitas pencatatan, bukan kualitas pekerjaan."
    ),
)
c.metric(
    "Entri overlap",
    kpis["overlap"],
    help=(
        "Jumlah entri unik yang terlibat pada dua rentang Actual Start–Actual Finish yang saling bertumpang tindih untuk pegawai yang sama. "
        "Overlap perlu dikonfirmasi karena bisa berupa aktivitas paralel yang wajar, meeting sambil bekerja, atau pencatatan waktu yang perlu diperbaiki."
    ),
)
d.metric(
    "Indikator efektivitas",
    f"{kpis['effectiveness']} / 100",
    help=(
        "Proxy gabungan kualitas pencatatan berdasarkan copy, Note minim, overlap, validasi durasi, dan aktivitas berulang-lama. "
        "Bukan ukuran produktivitas atau performa individu."
    ),
)
st.info(
    f"Audit memakai {kpis['total']} entri sesuai filter aktif. {kpis['minimal']} entri ({kpis['minimal_rate']}%) memiliki Note "
    f"dengan penjelasan minim; {kpis['duration']} entri memerlukan validasi durasi."
)
st.caption("Indikator di halaman ini adalah sinyal kualitas pencatatan. Validasi konteks tetap diperlukan sebelum mengambil keputusan.")

st.subheader("Rekomendasi")
if result["quality_llm"] is not None:
    explanation = result["quality_llm"]
    model_label = result.get("llm_model") or "LLM"
    st.caption(f"Narasi: {model_label}")
    st.write(explanation.summary)
    if explanation.observations:
        st.markdown("**Sinyal utama yang mendasari rekomendasi**")
        for item in explanation.observations:
            st.write(f"- {item}")
    if explanation.risks_or_attention_points:
        st.markdown("**Poin yang perlu didiskusikan manajemen**")
        for item in explanation.risks_or_attention_points:
            st.write(f"- {item}")
    if explanation.recommended_investigation:
        st.markdown("**Prioritas tindak lanjut / validasi**")
        for item in explanation.recommended_investigation:
            st.write(f"- {item}")
else:
    st.caption("LLM Off/tidak tersedia; rekomendasi deterministik tetap ditampilkan.")
    display_deterministic_recommendations(result["recommendations"])

with st.expander("Dasar rekomendasi deterministik", expanded=False):
    display_deterministic_recommendations(result["recommendations"])

if result["llm_error"]:
    st.warning("Rekomendasi LLM tidak tersedia, tetapi audit deterministik tetap selesai: " + result["llm_error"])
if result["embedding_error"]:
    st.warning("Audit deterministik selesai, tetapi relasi semantik tidak dapat dibuat: " + result["embedding_error"])

# Hide the duration tab when there is nothing to validate.
tab_labels = ["Penilaian entri", "Per anggota", "Aktivitas berulang", "Copy-paste", "Overlap"]
if not result["duration"].empty:
    tab_labels.append("Durasi")
tab_labels.extend(["Relasi semantik", "Topik"])
tab_objects = st.tabs(tab_labels)
tab_map = dict(zip(tab_labels, tab_objects))

with tab_map["Penilaian entri"]:
    st.caption("Skor dan kategori pada tab ini menilai kelengkapan pencatatan Note, bukan kualitas hasil kerja.")
    st.dataframe(result["entries"], use_container_width=True, hide_index=True)

with tab_map["Per anggota"]:
    st.markdown("**Cara membaca:** angka menunjukkan pola pencatatan pada filter aktif dan tidak digunakan sebagai ranking performa.")
    members = (
        result["entries"]
        .groupby("employee", as_index=False)
        .agg(
            entry_count=("row_id", "size"),
            total_hours=("hours", "sum"),
            copy_entry_count=("Indikasi copy", "sum"),
            minimal_note_count=("Kategori", lambda value: (value == "Minim").sum()),
        )
        .sort_values("total_hours", ascending=False)
        .rename(
            columns={
                "employee": "Pegawai",
                "entry_count": "Jumlah entri",
                "total_hours": "Total jam tercatat",
                "copy_entry_count": "Entri dengan indikasi copy",
                "minimal_note_count": "Entri dengan Note minim",
            }
        )
    )
    st.caption("'Entri dengan Note minim' = jumlah entri yang skor penulisannya masuk kategori Minim berdasarkan rule Python.")
    st.dataframe(members, use_container_width=True, hide_index=True)

with tab_map["Aktivitas berulang"]:
    st.caption("Menunjukkan aktivitas dengan nama task yang berulang pada pegawai yang sama. 'Cenderung lama' membandingkan median durasi task dengan P75 jam pegawai pada filter aktif.")
    st.dataframe(result["repeated"], use_container_width=True, hide_index=True)

with tab_map["Copy-paste"]:
    st.markdown(
        "**Cara membaca:** setiap baris adalah satu pasangan Note milik pegawai yang sama yang identik atau sangat mirip. "
        "Bandingkan langsung Aktivitas 1/2 dan Note 1/2 untuk memvalidasi apakah kemiripan wajar atau pencatatannya perlu diperkaya."
    )
    copy_columns = [
        "Pegawai",
        "Tanggal 1",
        "Aktivitas 1",
        "Note 1",
        "Jam 1",
        "Tanggal 2",
        "Aktivitas 2",
        "Note 2",
        "Jam 2",
        "Jenis",
        "Skor fuzzy",
        "Row 1",
        "Row 2",
    ]
    copy_table = result["copies"].reindex(columns=copy_columns)
    st.dataframe(copy_table.head(500), use_container_width=True, hide_index=True)

with tab_map["Overlap"]:
    with st.expander("Help — apa fungsi tabel Overlap dan bagaimana membacanya?", expanded=False):
        st.markdown(
            """
Tabel Overlap membantu memvalidasi dua entri **pegawai yang sama** yang waktunya saling bertumpang tindih.

Contoh: Aktivitas A tercatat 09:00–11:00 dan Aktivitas B 10:30–12:00, sehingga terdapat overlap 30 menit. Ini **bukan otomatis kesalahan**. Bisa terjadi karena meeting sambil melakukan aktivitas lain, kerja paralel, atau salah input waktu.

Baca **Aktivitas 1/2, waktu mulai-selesai, Note, dan Overlap menit** bersama-sama. Fokusnya adalah memastikan konteks dan mencegah double counting bila kedua durasi sebenarnya tidak berjalan paralel.
"""
        )
    st.dataframe(result["overlaps"], use_container_width=True, hide_index=True)

if "Durasi" in tab_map:
    with tab_map["Durasi"]:
        st.caption("Tab ini hanya muncul ketika terdapat entri yang Actual Start–Finish-nya tidak tersedia, negatif, atau berbeda dari jam tercatat di luar toleransi.")
        st.dataframe(result["duration"], use_container_width=True, hide_index=True)

with tab_map["Relasi semantik"]:
    with st.expander("Help — cara membaca relasi semantik", expanded=False):
        st.markdown(
            """
Embedding membandingkan makna **Task + Note**, bukan hanya kesamaan kata. Setiap baris menampilkan dua entri lengkap agar alasan kedekatannya dapat diperiksa.

- **Skor semantik** makin mendekati 1 berarti representasi maknanya makin dekat.
- **Dekat / Sangat dekat** adalah label bantu membaca skor.
- Relasi semantik **bukan bukti duplikasi**. Dua aktivitas berbeda dapat memiliki konteks yang memang serupa.
"""
        )
    st.dataframe(result["semantic"].head(1000), use_container_width=True, hide_index=True)

with tab_map["Topik"]:
    with st.expander("Help — apa itu Kelompok topik?", expanded=False):
        st.markdown(
            """
**Kelompok topik** adalah nomor cluster yang dibentuk Python dari kemiripan embedding Task + Note. Nomor 1, 2, 3, dan seterusnya **bukan ranking dan bukan skor kualitas**.

Agar lebih mudah dibaca, **Tema representatif** mengambil nama task yang paling sering muncul di cluster tersebut. Gunakan bersama jumlah entri, total jam, pegawai/proyek terkait, dan contoh Note untuk memahami tema aktivitas yang terkumpul.
"""
        )
    st.dataframe(result["topics"], use_container_width=True, hide_index=True)

output = io.BytesIO()
with pd.ExcelWriter(output, engine="openpyxl") as writer:
    pd.DataFrame(
        [
            ["Indikator", "Nilai"],
            ["Total entri", kpis["total"]],
            ["Copy/near-copy", kpis["copy"]],
            ["Copy rate", kpis["copy_rate"] / 100],
            ["Skor penulisan", kpis["writing"]],
            ["Overlap", kpis["overlap"]],
            ["Masalah durasi", kpis["duration"]],
            ["Efektivitas (proxy)", kpis["effectiveness"]],
        ]
    ).to_excel(writer, sheet_name="Ringkasan", index=False, header=False)
    result["entries"].to_excel(writer, sheet_name="Penilaian Entri", index=False)
    result["copies"].to_excel(writer, sheet_name="Copy Paste", index=False)
    result["overlaps"].to_excel(writer, sheet_name="Overlap", index=False)
    if not result["duration"].empty:
        result["duration"].to_excel(writer, sheet_name="Durasi", index=False)
    result["repeated"].to_excel(writer, sheet_name="Aktivitas Berulang", index=False)
    result["semantic"].to_excel(writer, sheet_name="Relasi Semantik", index=False)
    result["topics"].to_excel(writer, sheet_name="Topik", index=False)

st.download_button(
    "Unduh hasil audit (.xlsx)",
    output.getvalue(),
    "hasil_audit_kualitas_timesheet.xlsx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)
