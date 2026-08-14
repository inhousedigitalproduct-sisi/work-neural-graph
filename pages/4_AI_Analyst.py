from __future__ import annotations

import json

import pandas as pd
import streamlit as st

from src.analytics.service import AnalyticsService
from src.domain.models import GraphStrategy
from src.llm.client import OllamaError, OllamaMalformedResponseError
from src.llm.service import create_ai_analyst_service
from src.services import TimesheetDataService
from src.ui.components import render_shared_filters
from src.utils.config import get_config

config = get_config()
analytics_service = AnalyticsService(config.db_path)
dataset_service = TimesheetDataService(config.db_path)
ai_service = create_ai_analyst_service(
    config.db_path,
    config.ollama_host,
    config.ollama_model,
    config.ollama_timeout_seconds,
)


def filter_signature(filters) -> tuple:
    return (
        filters.start_date,
        filters.end_date,
        tuple(filters.employee_names),
        tuple(filters.projects),
        tuple(filters.task_keys),
        tuple(filters.states),
        filters.note_keyword,
    )


def build_scope_payload(snapshot, filters) -> dict:
    return {
        "filters": {
            "start_date": filters.start_date,
            "end_date": filters.end_date,
            "employees": list(filters.employee_names),
            "projects": list(filters.projects),
            "tasks": list(filters.task_keys),
        },
        "dataset": {
            "rows": int(snapshot.filtered_dataframe.shape[0]),
            "active_days": snapshot.kpi.active_days,
            "unique_tasks": snapshot.kpi.unique_tasks,
            "unique_employees": snapshot.kpi.unique_employees,
            "unique_projects": snapshot.kpi.unique_projects,
        },
    }


def build_llm_brief(snapshot, filters) -> dict:
    top_tasks = snapshot.fragmentation.head(5)[
        [
            "task",
            "project",
            "employees",
            "total_hours",
            "interruption_count",
            "total_interruption_days",
            "continuous_work_ratio",
            "fragmentation_score",
        ]
    ].copy()
    top_tasks["continuous_work_ratio"] = top_tasks["continuous_work_ratio"].round(3)
    top_tasks["total_hours"] = top_tasks["total_hours"].round(2)

    employee_summary = (
        snapshot.filtered_dataframe.groupby("employee", as_index=False)
        .agg(
            entries=("task", "size"),
            total_hours=("hours", "sum"),
            unique_tasks=("task_key", "nunique"),
            unique_projects=("project", "nunique"),
        )
        .sort_values("total_hours", ascending=False)
        .head(10)
    )
    employee_summary["total_hours"] = employee_summary["total_hours"].round(2)

    return {
        "scope": build_scope_payload(snapshot, filters),
        "kpi": {
            "total_hours": round(snapshot.kpi.total_hours, 2),
            "active_days": snapshot.kpi.active_days,
            "unique_tasks": snapshot.kpi.unique_tasks,
            "unique_employees": snapshot.kpi.unique_employees,
            "unique_projects": snapshot.kpi.unique_projects,
            "fragmented_tasks": snapshot.kpi.fragmented_tasks,
            "interrupted_tasks": snapshot.kpi.interrupted_tasks,
            "average_continuity_ratio": round(snapshot.kpi.average_continuity_ratio, 3),
        },
        "priority_tasks": top_tasks.to_dict(orient="records"),
        "employee_work_patterns": employee_summary.to_dict(orient="records"),
        "interpretation_guidance": {
            "audience": "manager / management",
            "principle": "describe work-pattern and timesheet signals; do not judge individual performance",
        },
    }


def build_recommendations(snapshot) -> list[str]:
    interrupted = snapshot.fragmentation[snapshot.fragmentation["interruption_count"] > 0]
    recommendations: list[str] = []
    if not interrupted.empty:
        task = interrupted.iloc[0]
        recommendations.append(
            f"Validasi konteks task '{task['task']}' terlebih dahulu karena memiliki {int(task['total_interruption_days'])} "
            f"hari jeda dan skor fragmentasi {int(task['fragmentation_score'])}. Cari apakah penyebabnya dependency, perubahan "
            "prioritas, karakter pekerjaan support, atau struktur task yang terlalu besar."
        )
    if snapshot.kpi.average_continuity_ratio < 0.5:
        recommendations.append(
            "Tinjau task dengan rentang kalender panjang namun hari aktif sedikit; pertimbangkan milestone/subtask agar progres, "
            "dependency, dan next step lebih mudah dipantau."
        )
    recommendations.append(
        "Gunakan hasil ini sebagai bahan diskusi manajemen dan sampling data, bukan sebagai penilaian performa individu."
    )
    return recommendations


st.title("AI Analyst")
st.caption("Ringkasan manajerial berbasis data timesheet aktif. Python menghitung fakta; Qwen hanya menjelaskan hasil.")

source_dataframe = dataset_service.load_active_dataset()
if source_dataframe.empty:
    st.info("Belum ada dataset aktif. Unggah file timesheet terlebih dahulu melalui halaman Load Data.")
    if st.button("Buka Load Data"):
        st.switch_page("pages/1_Load_Data.py")
    st.stop()

filters, _ = render_shared_filters(source_dataframe)
current_filter_signature = filter_signature(filters)
status = ai_service.get_status()
with st.sidebar:
    st.divider()
    st.subheader("Status analisis lokal")
    (st.success if status.available else st.warning)(f"Qwen {'siap' if status.available else 'tidak tersedia'}: {status.model}")
    st.caption("Ringkasan dasar tetap bisa dijalankan saat Qwen offline.")
    with st.expander("Cara kerja", expanded=False):
        st.markdown(
            "1. Memakai data dari Load Data.  \n"
            "2. Menerapkan filter.  \n"
            "3. Menghitung metrik secara deterministik.  \n"
            "4. Menyusun ringkasan dan rekomendasi.  \n"
            "5. Jika tersedia, Qwen menjelaskan hasil tanpa mengubah angka."
        )

question = st.text_area(
    "Pertanyaan untuk Qwen",
    placeholder="Contoh: pola kerja mana yang perlu saya review terlebih dahulu?",
    height=82,
)
use_qwen = st.checkbox(
    "Buat narasi manajerial dengan Qwen",
    value=True,
    help="Qwen menjelaskan ringkasan data yang sudah dihitung Python. Ia tidak menentukan atau mengubah angka.",
)

if st.button("Jalankan analisis", type="primary"):
    with st.status("Menyiapkan analisis timesheet…", expanded=True) as progress:
        st.write("Tahap 1/5 — Memuat data timesheet aktif dan menerapkan filter.")
        snapshot = analytics_service.build_snapshot(filters=filters, strategy=GraphStrategy.SEQUENTIAL)
        st.write(f"Tahap 2/5 — Menghitung metrik dari {len(snapshot.filtered_dataframe)} entri.")
        st.write("Tahap 3/5 — Mengidentifikasi continuity, jeda pengerjaan, dan task prioritas.")
        recommendations = build_recommendations(snapshot)
        st.write("Tahap 4/5 — Menyusun ringkasan dan rekomendasi berbasis data.")
        ai_result, ai_error = None, None
        if use_qwen and status.available:
            try:
                effective_question = question.strip() or (
                    "Berikan ringkasan eksekutif atas pola timesheet pada filter aktif. Jelaskan sinyal utama, hal yang perlu "
                    "didiskusikan manajemen, dan investigasi lanjutan. Bedakan fakta dari hipotesis dan jangan menilai individu."
                )
                brief = build_llm_brief(snapshot, filters)
                explanation, duration, _ = ai_service.explain_result(
                    question=effective_question,
                    result_payload=brief,
                )
                ai_result = {"explanation": explanation, "payload": brief, "duration": duration}
                st.write(f"Tahap 5/5 — Qwen menyiapkan narasi manajerial ({duration:.1f} detik).")
            except (OllamaError, OllamaMalformedResponseError, ValueError) as exc:
                ai_error = str(exc)
                st.write("Tahap 5/5 — Penjelasan Qwen tidak tersedia; ringkasan deterministik tetap selesai.")
        else:
            st.write("Tahap 5/5 — Narasi Qwen dilewati (dinonaktifkan atau model offline).")
        progress.update(label="Analisis selesai", state="complete", expanded=False)
    st.session_state["ai_analyst_result"] = {
        "snapshot": snapshot,
        "recommendations": recommendations,
        "ai_result": ai_result,
        "ai_error": ai_error,
        "filter_signature": current_filter_signature,
    }

result = st.session_state.get("ai_analyst_result")
if result is None:
    st.info("Pilih filter bila diperlukan, lalu tekan **Jalankan analisis**. Status proses akan tampil di halaman ini.")
    st.stop()
if result.get("filter_signature") != current_filter_signature:
    st.info("Filter berubah sejak analisis terakhir. Tekan **Jalankan analisis** kembali agar seluruh insight dan rekomendasi mengikuti filter aktif.")
    st.stop()

snapshot = result["snapshot"]
fragmentation = snapshot.fragmentation
interrupted = fragmentation[fragmentation["interruption_count"] > 0]
st.subheader("Ringkasan manajerial")
col1, col2, col3, col4 = st.columns(4)
col1.metric("Entri dianalisis", len(snapshot.filtered_dataframe))
col2.metric("Task terputus", len(interrupted))
col3.metric("Rata-rata continuity", f"{snapshot.kpi.average_continuity_ratio:.0%}")
col4.metric("Task unik", snapshot.kpi.unique_tasks)
if interrupted.empty:
    st.success("Tidak ada task dengan jeda pengerjaan pada filter yang dipilih.")
else:
    leading = interrupted.iloc[0]
    st.info(
        f"Dari {snapshot.kpi.unique_tasks} task pada filter aktif, {len(interrupted)} task memiliki jeda pengerjaan. "
        f"Prioritas validasi: **{leading['task']}** (skor {int(leading['fragmentation_score'])}, "
        f"jeda {int(leading['total_interruption_days'])} hari)."
    )

st.subheader("Rekomendasi")
for index, recommendation in enumerate(result["recommendations"], start=1):
    st.write(f"{index}. {recommendation}")

if result["ai_error"]:
    st.warning(f"Penjelasan Qwen tidak tersedia: {result['ai_error']}")
if result["ai_result"]:
    explanation = result["ai_result"]["explanation"]
    st.subheader("Penjelasan Qwen")
    st.write(explanation.summary)
    for heading, items in (
        ("Sinyal utama dari data", explanation.observations),
        ("Perlu tanggapan / diskusi manajemen", explanation.risks_or_attention_points),
        ("Pertanyaan untuk investigasi lanjutan", explanation.recommended_investigation),
    ):
        if items:
            st.markdown(f"**{heading}**")
            for item in items:
                st.write(f"- {item}")

tabs = st.tabs(["Task prioritas", "Per anggota", "Data filter"])
with tabs[0]:
    with st.expander("Help — cara membaca Task prioritas", expanded=False):
        st.markdown(
            """
Tabel ini mengurutkan task berdasarkan sinyal fragmentasi dari filter aktif. **Prioritas berarti perlu ditinjau konteksnya, bukan berarti task tersebut buruk.**

- **Jam**: total jam tercatat pada task.
- **Jumlah terputus**: berapa kali terdapat gap lebih dari satu hari antar kemunculan task.
- **Hari jeda**: total hari kosong di antara hari aktif task.
- **Continuity**: hari aktif dibagi rentang kalender; makin mendekati 1 berarti pola makin rapat.
- **Skor fragmentasi**: `continuation count + total interruption days`; makin tinggi, makin layak ditelusuri alasan jedanya.

Contoh: task dengan 20 hari jeda dan continuity rendah dapat menjadi prioritas diskusi untuk memastikan apakah ada dependency, perubahan prioritas, atau karakter support yang memang sporadis.
"""
        )
    priority = fragmentation[
        [
            "task",
            "project",
            "total_hours",
            "interruption_count",
            "total_interruption_days",
            "continuous_work_ratio",
            "fragmentation_score",
        ]
    ].copy()
    priority.columns = [
        "Task",
        "Proyek",
        "Jam",
        "Jumlah terputus",
        "Hari jeda",
        "Continuity",
        "Skor fragmentasi",
    ]
    st.dataframe(priority, use_container_width=True, hide_index=True)

with tabs[1]:
    with st.expander("Help — cara membaca Per anggota", expanded=False):
        st.markdown(
            """
Tabel ini hanya menunjukkan **pola pencatatan pada cakupan filter**, bukan nilai performa individu.

- **Pegawai**: nama pemilik entri timesheet.
- **Jumlah entri**: banyaknya baris timesheet pada filter aktif.
- **Total jam tercatat**: penjumlahan jam pada entri tersebut.
- **Jumlah task unik**: variasi task yang tercatat.
- **Jumlah proyek unik**: banyaknya proyek yang muncul pada entri pegawai.

Gunakan tabel untuk memahami distribusi aktivitas atau memilih sampel investigasi. Perbedaan angka dapat disebabkan peran, jenis pekerjaan, periode penugasan, atau aturan pencatatan yang berbeda.
"""
        )
    per_employee = (
        snapshot.filtered_dataframe.groupby("employee", as_index=False)
        .agg(
            entries=("task", "size"),
            total_hours=("hours", "sum"),
            unique_tasks=("task_key", "nunique"),
            unique_projects=("project", "nunique"),
        )
        .sort_values("total_hours", ascending=False)
        .rename(
            columns={
                "employee": "Pegawai",
                "entries": "Jumlah entri",
                "total_hours": "Total jam tercatat",
                "unique_tasks": "Jumlah task unik",
                "unique_projects": "Jumlah proyek unik",
            }
        )
    )
    st.dataframe(per_employee, use_container_width=True, hide_index=True)

with tabs[2]:
    st.caption("Filter yang membentuk hasil analisis saat ini.")
    st.json(build_scope_payload(snapshot, filters)["filters"])

with st.expander("Detail teknis untuk pengembangan", expanded=False):
    if result["ai_result"]:
        st.code(json.dumps(result["ai_result"]["payload"], indent=2, ensure_ascii=False), language="json")
