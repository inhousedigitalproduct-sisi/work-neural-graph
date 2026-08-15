from __future__ import annotations

import logging
from datetime import date, datetime

import pandas as pd
import streamlit as st

from src.database.repository import DuplicateImportError
from src.ingestion.mapper import REQUIRED_FIELDS, suggest_column_mapping
from src.ingestion.normalizer import NormalizationError
from src.quality.readiness import DatasetReadiness, build_dataset_readiness
from src.quality.timesheet_quality import (
    find_copy_pairs,
    find_duration_issues,
    find_overlap_pairs,
    managerial_summary,
    prepare_quality_dataframe,
)
from src.services import ImportService, TimesheetDataService
from src.ui.components import clear_dataset_dependent_state, render_validation_result
from src.utils.config import get_config

logger = logging.getLogger(__name__)
config = get_config()
service = ImportService(config.db_path)
dataset_service = TimesheetDataService(config.db_path)
DEFAULT_FUZZY_THRESHOLD = 0.90

MONTHS_ID = {
    1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "Mei", 6: "Jun",
    7: "Jul", 8: "Agu", 9: "Sep", 10: "Okt", 11: "Nov", 12: "Des",
}


def format_integer(value: int | float) -> str:
    return f"{int(round(float(value))):,}".replace(",", ".")


def format_hours(value: float) -> str:
    rounded = round(float(value), 1)
    return format_integer(int(rounded)) if rounded.is_integer() else str(rounded).replace(".", ",")


def format_date_id(value: date | datetime | pd.Timestamp | None) -> str:
    if value is None or pd.isna(value):
        return "-"
    timestamp = pd.Timestamp(value)
    return f"{timestamp.day} {MONTHS_ID[timestamp.month]} {timestamp.year}"


def format_datetime_id(value: object) -> str:
    if value is None or pd.isna(value):
        return "-"
    timestamp = pd.Timestamp(value)
    return f"{format_date_id(timestamp)} {timestamp.strftime('%H:%M')}"


@st.cache_data(show_spinner=False)
def cached_readiness(dataframe: pd.DataFrame) -> DatasetReadiness:
    return build_dataset_readiness(dataframe)


def dataset_signature(dataframe: pd.DataFrame) -> tuple:
    if dataframe.empty:
        return (0,)
    return (
        len(dataframe),
        str(pd.to_datetime(dataframe["work_date"], errors="coerce").min()),
        str(pd.to_datetime(dataframe["work_date"], errors="coerce").max()),
        round(float(pd.to_numeric(dataframe["hours"], errors="coerce").fillna(0).sum()), 4),
    )


def run_quality_audit(dataframe: pd.DataFrame, progress) -> dict[str, object]:
    prepared = prepare_quality_dataframe(dataframe)
    progress.progress(0.15, text="1/4 — Validasi durasi dan waktu")
    duration = find_duration_issues(prepared)

    progress.progress(0.30, text="2/4 — Deteksi exact copy dan near-copy")
    copies = find_copy_pairs(
        prepared,
        DEFAULT_FUZZY_THRESHOLD,
        lambda done, total: progress.progress(
            0.30 + 0.40 * (done / total if total else 1),
            text=f"2/4 — Fuzzy matching {done:,}/{total:,}",
        ),
    )

    progress.progress(0.75, text="3/4 — Pemeriksaan overlap")
    overlaps = find_overlap_pairs(prepared)

    progress.progress(0.90, text="4/4 — Kualitas Note dan aktivitas berulang")
    kpis, entries, repeated, _ = managerial_summary(prepared, copies, overlaps, duration)
    progress.progress(1.0, text="Audit kualitas selesai")
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


def build_preview(dataframe: pd.DataFrame) -> pd.DataFrame:
    preferred = ["work_date", "employee", "project", "task", "hours", "note"]
    existing = [column for column in preferred if column in dataframe.columns]
    preview = dataframe[existing].head(8).copy()
    if "work_date" in preview.columns:
        preview["work_date"] = pd.to_datetime(preview["work_date"], errors="coerce").map(format_date_id)
    if "hours" in preview.columns:
        preview["hours"] = pd.to_numeric(preview["hours"], errors="coerce").round(2)
    preview = preview.rename(columns={
        "work_date": "Tanggal", "employee": "Pegawai", "project": "Proyek",
        "task": "Task", "hours": "Jam", "note": "Note",
    })
    return preview


def render_readiness(readiness: DatasetReadiness) -> None:
    st.subheader("Data Readiness")
    st.caption("Validasi struktur dan sinyal awal sebelum dataset digunakan oleh seluruh modul analisis.")
    checks = [
        (readiness.required_columns_complete, "Struktur kolom utama lengkap", "Kolom utama belum lengkap"),
        (readiness.invalid_work_dates == 0, "Seluruh tanggal kerja dapat dibaca", f"{readiness.invalid_work_dates} tanggal tidak valid"),
        (readiness.missing_essential_values == 0, "Informasi utama siap digunakan", f"{readiness.missing_essential_values} entri memiliki informasi utama kosong/tidak valid"),
    ]
    for passed, ok_text, bad_text in checks:
        if passed:
            st.success(ok_text)
        else:
            st.warning(bad_text)
    if readiness.minimal_note_count:
        st.warning(f"{format_integer(readiness.minimal_note_count)} entri memiliki Note dengan penjelasan minim.")
    if readiness.overlap_pair_count:
        st.warning(f"{format_integer(readiness.overlap_pair_count)} pasangan aktivitas terindikasi overlap waktu.")
    elif readiness.timed_entry_count:
        st.success("Tidak ada overlap pada entri yang memiliki Actual Start–Finish.")
    else:
        st.info("Overlap belum dapat diperiksa karena Actual Start–Finish tidak tersedia.")


def render_dataset_overview(dataframe: pd.DataFrame) -> None:
    summary = dataset_service.get_dataset_summary(dataframe)
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Entri", format_integer(summary.row_count))
    c2.metric("Pegawai", format_integer(summary.employee_count))
    c3.metric("Proyek", format_integer(summary.project_count))
    c4.metric("Jam", format_hours(summary.total_hours))
    c5.metric("Periode", f"{format_date_id(summary.start_date)} → {format_date_id(summary.end_date)}")


def latest_import_metadata(history: pd.DataFrame) -> tuple[str, str]:
    if history.empty:
        return "Dataset aktif", ""
    latest = history.iloc[0]
    source_file = str(latest.get("source_file") or "Dataset aktif")
    imported_at = latest.get("imported_at")
    return source_file, format_datetime_id(imported_at) if imported_at is not None else ""


def render_navigation_actions(readiness: DatasetReadiness) -> None:
    st.caption("Dataset siap digunakan oleh modul berikut." if readiness.is_ready else "Perbaiki masalah struktur sebelum melanjutkan.")
    c1, c2, c3 = st.columns(3)
    if c1.button("Buka Neural Graph →", use_container_width=True, disabled=not readiness.is_ready):
        st.switch_page("pages/2_Neural_Graph.py")
    if c2.button("Buka Fragmentation →", use_container_width=True, disabled=not readiness.is_ready):
        st.switch_page("pages/3_Fragmentation.py")
    if c3.button("Buka Audit Kualitas →", type="primary", use_container_width=True, disabled=not readiness.is_ready):
        st.switch_page("pages/5_Quality_Audit.py")


def render_import_history(history: pd.DataFrame) -> None:
    if history.empty:
        st.info("Belum ada riwayat import.")
        return
    columns = [column for column in ["source_file", "imported_at", "row_count", "status", "source_hash"] if column in history.columns]
    view = history[columns].copy()
    if "imported_at" in view.columns:
        view["imported_at"] = pd.to_datetime(view["imported_at"]).map(format_datetime_id)
    if "source_hash" in view.columns:
        view["source_hash"] = view["source_hash"].astype(str).str[:12]
    st.dataframe(view, use_container_width=True, hide_index=True)


def render_reset_section() -> None:
    st.caption("Reset menghapus seluruh entri timesheet dan riwayat import.")
    if not st.session_state.get("load_data_confirm_reset"):
        if st.button("Reset Dataset"):
            st.session_state["load_data_confirm_reset"] = True
            st.rerun()
        return
    st.warning("Tindakan ini akan menghapus dataset aktif secara permanen.")
    st.text_input("Ketik RESET untuk konfirmasi", key="load_data_reset_text")
    c1, c2 = st.columns(2)
    if c1.button("Konfirmasi Reset", type="primary", disabled=st.session_state.get("load_data_reset_text", "") != "RESET"):
        service.reset_dataset()
        clear_dataset_dependent_state()
        st.session_state["load_data_flash"] = "Dataset berhasil di-reset."
        st.rerun()
    if c2.button("Batal Reset"):
        st.session_state.pop("load_data_confirm_reset", None)
        st.session_state.pop("load_data_reset_text", None)
        st.rerun()


def render_upload_section() -> None:
    st.subheader("Load Dataset")
    st.caption("Upload CSV/XLSX. Validasi struktur dan audit kualitas deterministic dijalankan sebelum dataset digunakan.")
    uploaded_file = st.file_uploader("Upload timesheet", type=["csv", "xlsx"], key="load_data_uploader")
    if uploaded_file is None:
        return

    try:
        content = uploaded_file.getvalue()
        raw_dataframe = service.load_raw_file(uploaded_file.name, content)
        import_detection = service.detect_import_mode(raw_dataframe)
        is_excel_template = bool(import_detection["is_template_candidate"])
        mapping: dict[str, str | None] = {}

        c1, c2, c3 = st.columns([2, 1, 1])
        c1.metric("File dipilih", uploaded_file.name)
        c2.metric("Baris input", format_integer(len(raw_dataframe)))
        c3.metric("Mode", "Template" if is_excel_template else "Mapping")

        with st.expander("Preview & struktur file", expanded=not is_excel_template):
            st.dataframe(raw_dataframe.head(20), use_container_width=True, hide_index=True)
            if is_excel_template:
                missing = import_detection["missing_required"]
                extras = import_detection["extra_columns"]
                if missing:
                    st.error("Kolom wajib yang belum ditemukan: " + ", ".join(missing))
                else:
                    st.success("Template dikenali dan seluruh kolom wajib tersedia.")
                if extras:
                    st.info("Kolom tambahan dipertahankan sebagai metadata: " + ", ".join(extras))
            else:
                suggested_mapping = suggest_column_mapping(raw_dataframe.columns.tolist())
                options = [""] + raw_dataframe.columns.tolist()
                mapping_columns = st.columns(2)
                for index, logical_field in enumerate(REQUIRED_FIELDS):
                    default_value = suggested_mapping.get(logical_field)
                    default_index = options.index(default_value) if default_value in options else 0
                    with mapping_columns[index % 2]:
                        selected = st.selectbox(
                            f"{logical_field.title()} column",
                            options=options,
                            index=default_index,
                            key=f"mapping_{logical_field}",
                        )
                    mapping[logical_field] = selected or None

        import_mode = st.radio(
            "Mode import",
            ["Replace current dataset", "Append to current dataset"],
            horizontal=True,
            key="load_data_import_mode",
        )

        if st.button("Validasi & Gunakan Dataset Ini", type="primary", use_container_width=True):
            with st.status("Memvalidasi dataset dan menjalankan audit kualitas…", expanded=True) as status:
                progress = st.progress(0.0, text="Menyiapkan validasi")
                if is_excel_template:
                    mapped_dataframe, template_warnings = service.prepare_template_dataframe(raw_dataframe)
                else:
                    mapped_dataframe = service.apply_mapping(raw_dataframe, mapping)
                    template_warnings = []

                progress.progress(0.05, text="Normalisasi dataset")
                entries, warnings, source_hash = service.normalize_entries(mapped_dataframe, uploaded_file.name, content)
                render_validation_result([], template_warnings + warnings)
                replace_existing = import_mode == "Replace current dataset"
                service.save_entries(uploaded_file.name, source_hash, entries, replace_existing=replace_existing)

                clear_dataset_dependent_state()
                active_dataset = dataset_service.load_active_dataset()
                audit_result = run_quality_audit(active_dataset, progress)
                st.session_state["quality_audit_result"] = audit_result
                st.session_state.pop("quality_semantic_result", None)
                status.update(label="Dataset tervalidasi dan audit kualitas selesai", state="complete", expanded=False)

            st.session_state["load_data_flash"] = (
                f"{format_integer(len(entries))} entri berhasil divalidasi. "
                "Audit kualitas deterministic juga sudah selesai dan tersedia di halaman Audit Kualitas."
            )
            st.rerun()

    except DuplicateImportError as exc:
        logger.info("Duplicate import prevented for %s", uploaded_file.name)
        st.warning(str(exc))
    except (ValueError, NormalizationError) as exc:
        logger.exception("Validation or normalization failed")
        st.error(str(exc))
    except Exception as exc:
        logger.exception("Unexpected import failure")
        st.error(f"Import gagal: {exc}")


st.title("Load & Validate Timesheet")
st.caption(
    "Halaman ini menjadi satu pintu untuk upload, validasi struktur, audit kualitas deterministic, "
    "dan aktivasi dataset sebelum digunakan oleh modul analisis lain."
)

flash_message = st.session_state.pop("load_data_flash", None)
if flash_message:
    st.success(flash_message)

current_dataset = dataset_service.load_active_dataset()
import_history = dataset_service.load_import_history()

if not current_dataset.empty:
    source_file, imported_text = latest_import_metadata(import_history)
    st.info(f"Dataset aktif: **{source_file}**" + (f" • impor terakhir {imported_text}" if imported_text else ""))

render_upload_section()

current_dataset = dataset_service.load_active_dataset()
if current_dataset.empty:
    st.info("Belum ada dataset aktif. Upload file untuk memulai analisis.")
else:
    st.divider()
    st.subheader("Dataset Overview")
    render_dataset_overview(current_dataset)
    readiness = cached_readiness(current_dataset)
    left, right = st.columns([0.9, 1.4])
    with left:
        render_readiness(readiness)
    with right:
        st.subheader("Preview Dataset")
        st.dataframe(build_preview(current_dataset), use_container_width=True, hide_index=True, height=330)
    render_navigation_actions(readiness)

st.divider()
with st.expander("Pengelolaan Dataset & Riwayat Import", expanded=False):
    st.markdown("#### Riwayat Import")
    render_import_history(import_history)
    st.divider()
    st.markdown("#### Reset Dataset")
    render_reset_section()
