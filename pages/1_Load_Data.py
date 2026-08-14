from __future__ import annotations

import html
import logging
from datetime import date, datetime

import pandas as pd
import streamlit as st

from src.database.repository import DuplicateImportError
from src.ingestion.mapper import REQUIRED_FIELDS, suggest_column_mapping
from src.ingestion.normalizer import NormalizationError
from src.quality.readiness import DatasetReadiness, build_dataset_readiness
from src.services import ImportService, TimesheetDataService
from src.ui.components import clear_dataset_dependent_state, render_validation_result
from src.utils.config import get_config

logger = logging.getLogger(__name__)

config = get_config()
service = ImportService(config.db_path)
dataset_service = TimesheetDataService(config.db_path)


MONTHS_ID = {
    1: "Jan",
    2: "Feb",
    3: "Mar",
    4: "Apr",
    5: "Mei",
    6: "Jun",
    7: "Jul",
    8: "Agu",
    9: "Sep",
    10: "Okt",
    11: "Nov",
    12: "Des",
}



def render_page_styles() -> None:
    st.markdown(
        """
        <style>
        .block-container {
            padding-top: 1.35rem;
            padding-bottom: 2.5rem;
            max-width: 1500px;
        }
        .wng-hero { margin: 0 0 1rem 0; }
        .wng-hero h1 {
            margin: 0;
            font-size: clamp(2rem, 2.8vw, 2.7rem);
            line-height: 1.08;
            letter-spacing: -0.025em;
        }
        .wng-hero p {
            margin: 0.55rem 0 0 0;
            color: #94a3b8;
            font-size: 0.95rem;
            max-width: 980px;
        }
        .wng-eyebrow {
            color: #8da2c7;
            font-size: 0.75rem;
            font-weight: 750;
            letter-spacing: 0.10em;
            text-transform: uppercase;
            margin-bottom: 0.25rem;
        }
        .wng-status-ready, .wng-status-warning {
            display: inline-flex;
            align-items: center;
            gap: 0.35rem;
            border-radius: 999px;
            padding: 0.3rem 0.72rem;
            font-size: 0.8rem;
            font-weight: 700;
        }
        .wng-status-ready {
            color: #a7f3d0;
            background: rgba(16, 185, 129, 0.14);
            border: 1px solid rgba(16, 185, 129, 0.30);
        }
        .wng-status-warning {
            color: #fde68a;
            background: rgba(245, 158, 11, 0.12);
            border: 1px solid rgba(245, 158, 11, 0.28);
        }
        .wng-file-name {
            font-size: 1.05rem;
            font-weight: 750;
            margin-bottom: 0.28rem;
            overflow-wrap: anywhere;
        }
        .wng-muted { color: #94a3b8; font-size: 0.82rem; }
        .wng-upload-lead {
            display: flex;
            gap: 0.8rem;
            align-items: center;
            margin: 0.1rem 0 0.7rem 0;
        }
        .wng-upload-icon {
            display: grid;
            place-items: center;
            width: 42px;
            height: 42px;
            border-radius: 12px;
            color: #bfdbfe;
            background: rgba(59, 130, 246, 0.12);
            border: 1px solid rgba(96, 165, 250, 0.24);
            font-size: 1.25rem;
            flex: 0 0 auto;
        }
        .wng-upload-title { font-size: 1.08rem; font-weight: 750; margin-bottom: 0.1rem; }
        .wng-check-row {
            display: flex;
            gap: 0.55rem;
            align-items: flex-start;
            padding: 0.42rem 0;
            border-bottom: 1px solid rgba(148, 163, 184, 0.10);
            line-height: 1.32;
            font-size: 0.91rem;
        }
        .wng-check-row:last-child { border-bottom: 0; }
        .wng-ok { color: #86efac; font-weight: 800; }
        .wng-warn { color: #fbbf24; font-weight: 800; }
        .wng-info { color: #93c5fd; font-weight: 800; }
        .wng-kpi-card {
            min-height: 118px;
            border: 1px solid rgba(148, 163, 184, 0.20);
            border-radius: 0.85rem;
            padding: 0.82rem 0.9rem;
            background: linear-gradient(145deg, rgba(15, 23, 42, 0.36), rgba(15, 23, 42, 0.18));
            display: flex;
            flex-direction: column;
            justify-content: space-between;
        }
        .wng-kpi-top { display: flex; align-items: center; gap: 0.55rem; }
        .wng-kpi-icon {
            width: 30px;
            height: 30px;
            border-radius: 9px;
            display: grid;
            place-items: center;
            background: rgba(59, 130, 246, 0.10);
            border: 1px solid rgba(96, 165, 250, 0.18);
            color: #bfdbfe;
            font-size: 0.92rem;
        }
        .wng-kpi-label { color: #cbd5e1; font-size: 0.80rem; font-weight: 650; }
        .wng-kpi-value {
            color: #f8fafc;
            font-size: 1.72rem;
            font-weight: 750;
            line-height: 1.0;
            margin-top: 0.5rem;
            letter-spacing: -0.02em;
            white-space: normal;
            overflow-wrap: anywhere;
        }
        .wng-kpi-value-period { font-size: 1.02rem; line-height: 1.23; }
        .wng-kpi-sub { color: #7f8ea3; font-size: 0.72rem; margin-top: 0.42rem; }
        .wng-note-icon {
            width: 36px;
            height: 36px;
            border-radius: 50%;
            display: grid;
            place-items: center;
            color: #bfdbfe;
            background: rgba(59, 130, 246, 0.10);
            border: 1px solid rgba(96, 165, 250, 0.18);
            flex: 0 0 auto;
            font-weight: 800;
        }
        .wng-ready-strip {
            height: 100%;
            min-height: 48px;
            border: 1px solid rgba(16, 185, 129, 0.24);
            background: rgba(16, 185, 129, 0.07);
            border-radius: 0.72rem;
            padding: 0.65rem 0.85rem;
            display: flex;
            align-items: center;
            gap: 0.55rem;
            color: #bbf7d0;
            font-size: 0.86rem;
            font-weight: 650;
        }
        section[data-testid="stFileUploaderDropzone"] {
            background: rgba(15, 23, 42, 0.28);
            border: 1px dashed rgba(96, 165, 250, 0.38);
            border-radius: 0.72rem;
            padding-top: 0.55rem;
            padding-bottom: 0.55rem;
        }
        section[data-testid="stFileUploaderDropzone"] button {
            border-color: rgba(96, 165, 250, 0.38);
        }
        div[data-testid="stVerticalBlockBorderWrapper"] {
            border-color: rgba(148, 163, 184, 0.20);
            background: rgba(15, 23, 42, 0.10);
        }
        div[data-testid="stDataFrame"] {
            border-radius: 0.65rem;
            overflow: hidden;
        }
        div.stButton > button { border-radius: 0.65rem; }
        @media (max-width: 900px) {
            .block-container { padding-top: 1rem; }
            .wng-kpi-card { min-height: 104px; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

def format_integer(value: int | float) -> str:
    return f"{int(round(float(value))):,}".replace(",", ".")


def format_hours(value: float) -> str:
    rounded = round(float(value), 1)
    if rounded.is_integer():
        return format_integer(int(rounded))
    whole, decimal = f"{rounded:,.1f}".split(".")
    return f"{whole.replace(',', '.')},{decimal}"


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


def latest_import_metadata(history: pd.DataFrame) -> tuple[str, str]:
    if history.empty:
        return "Dataset aktif", ""
    latest = history.iloc[0]
    source_file = str(latest.get("source_file") or "Dataset aktif")
    imported_at = latest.get("imported_at")
    imported_text = format_datetime_id(imported_at) if imported_at is not None else ""
    return source_file, imported_text



def render_kpi_card(
    *,
    icon: str,
    label: str,
    value: str,
    subtext: str,
    help_text: str,
    period: bool = False,
) -> None:
    value_class = "wng-kpi-value wng-kpi-value-period" if period else "wng-kpi-value"
    help_attr = html.escape(help_text, quote=True)
    st.markdown(
        f"""<div class="wng-kpi-card" title="{help_attr}">
            <div>
                <div class="wng-kpi-top">
                    <div class="wng-kpi-icon">{html.escape(icon)}</div>
                    <div class="wng-kpi-label">{html.escape(label)}</div>
                </div>
                <div class="{value_class}">{value}</div>
            </div>
            <div class="wng-kpi-sub">{html.escape(subtext)}</div>
        </div>""",
        unsafe_allow_html=True,
    )



def render_dataset_kpis(dataframe: pd.DataFrame) -> None:
    summary = dataset_service.get_dataset_summary(dataframe)
    columns = st.columns(5, gap="medium")
    with columns[0]:
        render_kpi_card(
            icon="▤",
            label="Entri",
            value=format_integer(summary.row_count),
            subtext="Total baris timesheet",
            help_text="Jumlah baris timesheet pada dataset aktif.",
        )
    with columns[1]:
        render_kpi_card(
            icon="◎",
            label="Pegawai",
            value=format_integer(summary.employee_count),
            subtext="Pegawai unik",
            help_text="Jumlah pegawai unik pada dataset aktif.",
        )
    with columns[2]:
        render_kpi_card(
            icon="◇",
            label="Proyek",
            value=format_integer(summary.project_count),
            subtext="Proyek unik",
            help_text="Jumlah proyek unik pada dataset aktif.",
        )
    with columns[3]:
        render_kpi_card(
            icon="◷",
            label="Jam",
            value=format_hours(summary.total_hours),
            subtext="Total jam tercatat",
            help_text="Total jam tercatat pada dataset aktif.",
        )
    with columns[4]:
        start_date = format_date_id(summary.start_date)
        end_date = format_date_id(summary.end_date)
        period_value = f"{html.escape(start_date)}<br>→ {html.escape(end_date)}"
        render_kpi_card(
            icon="⌁",
            label="Periode data",
            value=period_value,
            period=True,
            subtext="Tanggal awal → akhir",
            help_text="Rentang tanggal paling awal sampai paling akhir pada dataset aktif.",
        )

def readiness_row(symbol_class: str, symbol: str, text: str) -> None:
    st.markdown(
        f'<div class="wng-check-row"><span class="{symbol_class}">{symbol}</span><span>{html.escape(text)}</span></div>',
        unsafe_allow_html=True,
    )



def render_readiness(readiness: DatasetReadiness) -> None:
    st.subheader("Data Readiness")
    st.caption("Validasi struktur dan sinyal awal kualitas sebelum dataset dipakai untuk analisis.")
    if not readiness.is_ready:
        st.warning("Dataset belum siap dianalisis penuh. Perbaiki item struktural yang ditandai di bawah.")

    if readiness.required_columns_complete:
        readiness_row("wng-ok", "✓", "Struktur kolom utama lengkap")
    else:
        readiness_row(
            "wng-warn",
            "!",
            "Kolom utama belum lengkap: " + ", ".join(readiness.missing_required_columns),
        )

    if readiness.invalid_work_dates == 0:
        readiness_row("wng-ok", "✓", "Seluruh tanggal kerja dapat dibaca")
    else:
        readiness_row("wng-warn", "!", f"{format_integer(readiness.invalid_work_dates)} entri memiliki tanggal tidak valid")

    if readiness.missing_essential_values == 0:
        readiness_row("wng-ok", "✓", "Pegawai, proyek, task, tanggal, dan jam siap digunakan")
    else:
        readiness_row(
            "wng-warn",
            "!",
            f"{format_integer(readiness.missing_essential_values)} entri memiliki informasi utama yang kosong/tidak valid",
        )

    if readiness.minimal_note_count:
        readiness_row(
            "wng-warn",
            "!",
            f"{format_integer(readiness.minimal_note_count)} entri memiliki Note dengan penjelasan minim",
        )
    else:
        readiness_row("wng-ok", "✓", "Tidak ada sinyal Note minim dari pemeriksaan awal")

    if readiness.overlap_pair_count:
        readiness_row(
            "wng-warn",
            "!",
            f"{format_integer(readiness.overlap_pair_count)} pasangan aktivitas terindikasi overlap waktu",
        )
    elif readiness.timed_entry_count:
        readiness_row("wng-ok", "✓", "Tidak ada overlap pada entri yang memiliki Actual Start–Finish")
    else:
        readiness_row("wng-info", "i", "Overlap belum dapat diperiksa karena Actual Start–Finish tidak tersedia")

    coverage = readiness.timed_entry_coverage * 100
    readiness_row(
        "wng-info",
        "i",
        f"Cakupan data waktu untuk pemeriksaan overlap: {coverage:.1f}% dari dataset",
    )

    with st.expander("Cara membaca Data Readiness", expanded=False):
        st.markdown(
            """
            **Data Readiness** menjawab apakah dataset secara struktur dapat dipakai oleh Work Neural Graph.

            - **Hijau** berarti struktur/fakta dasar siap digunakan.
            - **Kuning** adalah sinyal yang perlu diperhatikan, tetapi tidak otomatis membuat dataset tidak layak dianalisis.
            - **Note minim** berkaitan dengan kualitas konteks pencatatan, bukan kualitas hasil kerja pegawai.
            - **Overlap** berarti dua rentang Actual Start–Finish milik pegawai yang sama saling bertumpang tindih dan perlu dikonfirmasi konteksnya.
            - Audit lebih detail tetap dilakukan melalui **Audit Kualitas**.
            """
        )


def build_preview(dataframe: pd.DataFrame) -> pd.DataFrame:
    preferred = ["work_date", "employee", "project", "task", "hours", "note"]
    existing = [column for column in preferred if column in dataframe.columns]
    preview = dataframe[existing].head(8).copy()
    if "work_date" in preview.columns:
        preview["work_date"] = pd.to_datetime(preview["work_date"], errors="coerce").map(format_date_id)
    if "hours" in preview.columns:
        preview["hours"] = pd.to_numeric(preview["hours"], errors="coerce").round(2)
    for text_column in ["employee", "project", "task", "note"]:
        if text_column in preview.columns:
            preview[text_column] = (
                preview[text_column]
                .fillna("")
                .astype(str)
                .str.strip()
                .replace({"": "-", "nan": "-", "None": "-"})
            )
    preview = preview.rename(
        columns={
            "work_date": "Tanggal",
            "employee": "Pegawai",
            "project": "Proyek",
            "task": "Task",
            "hours": "Jam",
            "note": "Note",
        }
    )
    return preview


def render_analysis_notes(readiness: DatasetReadiness) -> None:
    messages: list[str] = []

    if readiness.is_ready:
        messages.append("Dataset secara struktur sudah siap digunakan oleh seluruh modul analisis.")
    else:
        messages.append("Dataset belum siap dianalisis penuh karena masih ada masalah struktur atau data utama yang perlu diperbaiki.")

    if readiness.minimal_note_count:
        messages.append(
            f"Terdapat **{format_integer(readiness.minimal_note_count)} entri dengan Note minim**; analitik numerik tetap dapat berjalan, tetapi interpretasi konteks aktivitas dapat lebih terbatas."
        )

    if readiness.overlap_pair_count:
        messages.append(
            f"Terdapat **{format_integer(readiness.overlap_pair_count)} pasangan indikasi overlap waktu**. Ini bukan otomatis kesalahan dan perlu dikonfirmasi melalui Audit Kualitas."
        )
    elif readiness.timed_entry_count == 0:
        messages.append("Pemeriksaan overlap belum tersedia karena dataset tidak memiliki rentang Actual Start–Finish yang dapat dibandingkan.")

    if 0 < readiness.timed_entry_coverage < 1:
        messages.append(
            f"Pemeriksaan overlap mencakup **{readiness.timed_entry_coverage * 100:.1f}%** entri yang mempunyai Actual Start dan Actual Finish."
        )

    icon_col, content_col = st.columns([0.07, 0.93], gap="small")
    with icon_col:
        st.markdown('<div class="wng-note-icon">i</div>', unsafe_allow_html=True)
    with content_col:
        st.markdown("#### Yang perlu diketahui sebelum analisis")
        for message in messages:
            st.markdown(f"- {message}")


def render_navigation_actions(readiness: DatasetReadiness) -> None:
    status_col, neural_col, frag_col, ai_col = st.columns([1.05, 1, 1.25, 1], gap="small")
    with status_col:
        status_text = "✓ Dataset siap digunakan" if readiness.is_ready else "! Dataset belum siap"
        st.markdown(f'<div class="wng-ready-strip">{html.escape(status_text)}</div>', unsafe_allow_html=True)
    with neural_col:
        if st.button("Buka Neural Graph →", use_container_width=True, disabled=not readiness.is_ready):
            st.switch_page("pages/2_Neural_Graph.py")
    with frag_col:
        if st.button("Buka Fragmentation →", use_container_width=True, disabled=not readiness.is_ready):
            st.switch_page("pages/3_Fragmentation.py")
    with ai_col:
        if st.button("Buka AI Analyst →", type="primary", use_container_width=True, disabled=not readiness.is_ready):
            st.switch_page("pages/4_AI_Analyst.py")

def render_import_history(history: pd.DataFrame) -> None:
    st.markdown("#### Riwayat Import")
    if history.empty:
        st.info("Belum ada riwayat import.")
        return

    history_view = history[["source_file", "imported_at", "row_count", "status", "source_hash"]].copy()
    history_view["imported_at"] = pd.to_datetime(history_view["imported_at"]).map(format_datetime_id)
    history_view["source_hash"] = history_view["source_hash"].astype(str).str[:12]
    history_view.columns = ["File sumber", "Waktu import", "Jumlah entri", "Status", "Hash"]
    st.dataframe(history_view, use_container_width=True, hide_index=True)


def render_reset_section() -> None:
    st.markdown("#### Reset Dataset")
    st.caption("Reset menghapus seluruh entri timesheet dan riwayat import. Schema database dan konfigurasi tidak dihapus.")

    if not st.session_state.get("load_data_confirm_reset"):
        if st.button("Reset Dataset", key="load_data_reset_button"):
            st.session_state["load_data_confirm_reset"] = True
            st.rerun()
        return

    st.warning("Tindakan ini akan menghapus dataset aktif dan riwayat import secara permanen.")
    st.text_input("Ketik RESET untuk konfirmasi", key="load_data_reset_text")
    col1, col2 = st.columns(2)
    with col1:
        if st.button(
            "Konfirmasi Reset",
            type="primary",
            disabled=st.session_state.get("load_data_reset_text", "") != "RESET",
        ):
            service.reset_dataset()
            clear_dataset_dependent_state()
            st.session_state["load_data_flash"] = "Dataset berhasil di-reset. Seluruh entri dan riwayat import telah dihapus."
            st.rerun()
    with col2:
        if st.button("Batal Reset"):
            st.session_state.pop("load_data_confirm_reset", None)
            st.session_state.pop("load_data_reset_text", None)
            st.rerun()


def render_upload_section(current_dataset: pd.DataFrame, import_history: pd.DataFrame) -> None:
    with st.container(border=True):
        upload_col, status_col = st.columns([1.45, 1])
        with upload_col:
            st.markdown('<div class="wng-eyebrow">Load Dataset</div>', unsafe_allow_html=True)
            st.markdown(
                '<div class="wng-upload-lead"><div class="wng-upload-icon">⇧</div>'
                '<div><div class="wng-upload-title">Drag & drop file timesheet</div>'
                '<div class="wng-muted">CSV/XLSX · File baru divalidasi sebelum mengganti dataset aktif.</div></div></div>',
                unsafe_allow_html=True,
            )
            uploaded_file = st.file_uploader(
                "Upload timesheet file",
                type=["csv", "xlsx"],
                key="load_data_uploader",
                label_visibility="collapsed",
            )

        with status_col:
            st.markdown('<div class="wng-eyebrow">Dataset aktif</div>', unsafe_allow_html=True)
            if current_dataset.empty:
                st.markdown('<div class="wng-file-name">Belum ada dataset</div>', unsafe_allow_html=True)
                st.markdown('<div class="wng-muted">Upload file untuk memulai analisis.</div>', unsafe_allow_html=True)
                st.markdown('<br><span class="wng-status-warning">! Belum siap</span>', unsafe_allow_html=True)
            else:
                source_file, imported_text = latest_import_metadata(import_history)
                active_readiness = cached_readiness(current_dataset)
                st.markdown(f'<div class="wng-file-name">{html.escape(source_file)}</div>', unsafe_allow_html=True)
                metadata = f"Impor terakhir: {imported_text}" if imported_text else f"{format_integer(len(current_dataset))} entri aktif"
                st.markdown(f'<div class="wng-muted">{html.escape(metadata)}</div>', unsafe_allow_html=True)
                if active_readiness.is_ready:
                    st.markdown('<br><span class="wng-status-ready">✓ Siap dianalisis</span>', unsafe_allow_html=True)
                else:
                    st.markdown('<br><span class="wng-status-warning">! Perlu perbaikan</span>', unsafe_allow_html=True)

    if uploaded_file is None:
        return

    try:
        content = uploaded_file.getvalue()
        raw_dataframe = service.load_raw_file(uploaded_file.name, content)
        import_detection = service.detect_import_mode(raw_dataframe)
        is_excel_template = bool(import_detection["is_template_candidate"])
        mapping: dict[str, str | None] = {}

        with st.container(border=True):
            st.markdown('<div class="wng-eyebrow">Validasi File Baru</div>', unsafe_allow_html=True)
            info_cols = st.columns([2, 1, 1])
            info_cols[0].metric("File dipilih", uploaded_file.name)
            info_cols[1].metric("Baris input", format_integer(len(raw_dataframe)))
            info_cols[2].metric("Mode", "Template" if is_excel_template else "Mapping")

            with st.expander("Preview & struktur file", expanded=not is_excel_template):
                st.dataframe(raw_dataframe.head(20), use_container_width=True, hide_index=True)
                if is_excel_template:
                    missing = import_detection["missing_required"]
                    extras = import_detection["extra_columns"]
                    if not missing:
                        st.success("Template dikenali dan seluruh kolom wajib tersedia.")
                    else:
                        st.error("Kolom wajib yang belum ditemukan: " + ", ".join(missing))
                    if extras:
                        st.info("Kolom tambahan akan dipertahankan sebagai metadata: " + ", ".join(extras))
                else:
                    st.caption("File bukan template standar. Cocokkan kolom sumber ke field logis berikut.")
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

            with st.expander("Pengaturan import", expanded=False):
                import_mode = st.radio(
                    "Mode import",
                    options=["Replace current dataset", "Append to current dataset"],
                    index=0,
                    horizontal=True,
                    key="load_data_import_mode",
                    help="Replace adalah mode yang direkomendasikan. Dataset lama baru diganti setelah validasi dan normalisasi file baru berhasil.",
                )
                st.caption("Gunakan Append hanya jika file baru memang merupakan tambahan periode/baris yang belum ada pada dataset aktif.")

            if st.button("Validasi & Gunakan Dataset Ini", type="primary", use_container_width=True):
                if is_excel_template:
                    mapped_dataframe, template_warnings = service.prepare_template_dataframe(raw_dataframe)
                else:
                    mapped_dataframe = service.apply_mapping(raw_dataframe, mapping)
                    template_warnings = []

                entries, warnings, source_hash = service.normalize_entries(
                    mapped_dataframe,
                    uploaded_file.name,
                    content,
                )
                render_validation_result([], template_warnings + warnings)
                replace_existing = import_mode == "Replace current dataset"
                service.save_entries(
                    uploaded_file.name,
                    source_hash,
                    entries,
                    replace_existing=replace_existing,
                )
                clear_dataset_dependent_state()
                st.session_state["load_data_flash"] = (
                    f"{format_integer(len(entries))} entri dari {uploaded_file.name} berhasil divalidasi dan "
                    f"{'menggantikan dataset aktif' if replace_existing else 'ditambahkan ke dataset aktif'}."
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


def render_active_dataset(current_dataset: pd.DataFrame) -> None:
    if current_dataset.empty:
        with st.container(border=True):
            st.markdown("### Belum ada dataset aktif")
            st.write("Upload timesheet di atas. Setelah struktur dan isi utama tervalidasi, ringkasan readiness dan shortcut analisis akan muncul di halaman ini.")
        return

    readiness = cached_readiness(current_dataset)

    st.markdown('<div class="wng-eyebrow">Dataset Overview</div>', unsafe_allow_html=True)
    render_dataset_kpis(current_dataset)

    left, right = st.columns([0.92, 1.58], gap="large")
    with left:
        with st.container(border=True):
            render_readiness(readiness)
    with right:
        with st.container(border=True):
            st.subheader("Preview Dataset")
            st.caption(f"Contoh {min(8, len(current_dataset))} dari {format_integer(len(current_dataset))} entri aktif untuk verifikasi cepat.")
            st.dataframe(
                build_preview(current_dataset),
                use_container_width=True,
                hide_index=True,
                height=302,
                column_config={
                    "Tanggal": st.column_config.TextColumn(width="small"),
                    "Pegawai": st.column_config.TextColumn(width="medium"),
                    "Proyek": st.column_config.TextColumn(width="medium"),
                    "Task": st.column_config.TextColumn(width="large"),
                    "Jam": st.column_config.NumberColumn(width="small", format="%.2f"),
                    "Note": st.column_config.TextColumn(width="large"),
                },
            )

    with st.container(border=True):
        render_analysis_notes(readiness)

    render_navigation_actions(readiness)


render_page_styles()
st.markdown(
    '<div class="wng-hero"><h1>Load &amp; Validate Timesheet</h1>'
    '<p>Masukkan dataset timesheet, validasi strukturnya, lalu lanjutkan ke analisis. Halaman ini menjadi gerbang readiness sebelum data dipakai oleh seluruh modul Work Neural Graph.</p></div>',
    unsafe_allow_html=True,
)

flash_message = st.session_state.pop("load_data_flash", None)
if flash_message:
    st.success(flash_message)

current_dataset = dataset_service.load_active_dataset()
import_history = dataset_service.load_import_history()

render_upload_section(current_dataset, import_history)
render_active_dataset(current_dataset)

st.divider()
with st.expander("Pengelolaan Dataset & Riwayat Import", expanded=False):
    render_import_history(import_history)
    st.divider()
    render_reset_section()
