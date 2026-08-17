# Load Data Architecture

## Purpose

Load Data adalah entry point dataset timesheet: membaca file, menentukan import mode/mapping, melakukan normalization/validation, menyimpan dataset ke SQLite, menampilkan readiness, dan menyediakan navigasi ke modul analisis.

## Business Flow

```text
Upload file
 -> load_timesheet_file
 -> detect template / column mapping
 -> validate mapping or template
 -> normalize entries
 -> hash source
 -> repository save/replace
 -> clear dataset cache
 -> load active dataset
 -> readiness + preview + quality signals
 -> analysis modules
```

Page juga menjalankan quality preview (duration, copy/near-copy, overlap, repeated activity) untuk memberi sinyal awal sebelum user masuk ke Quality Audit.

## Entry Points and Dependencies

- Entry point: `pages/1_Load_Data.py`.
- Application services: `ImportService`, `TimesheetDataService` di `src/services.py`.
- Ingestion: `src/ingestion/loader.py`, `mapper.py`, `normalizer.py`, `validator.py`.
- Persistence: `src/database/repository.py`, `sqlite.py`.
- Quality/readiness: `src/quality/readiness.py`, sebagian `timesheet_quality.py`.
- Shared UI: `src/ui/components.py`.

## Current Risks and Non-standard Code

- Page cukup besar dan mengandung formatting helper, quality orchestration, readiness rendering, history rendering, serta import UI dalam satu file.
- Deterministic quality pipeline pada Load Data mirip dengan pipeline di Quality Audit sehingga berpotensi drift.
- `ImportService.save_entries` melakukan `st.cache_data.clear()`, sehingga service layer mengetahui Streamlit; ini melanggar target separation.
- `TimesheetDataService` membangun `ImportService` hanya untuk mendapatkan repository, menambah construction coupling.

## Refactor Recommendations

1. Extract `QualityAuditService` deterministic pipeline dan reuse dari Load Data + Quality Audit.
2. Pindahkan cache invalidation ke presentation/cache adapter, bukan persistence-oriented service.
3. Split `src/services.py` menjadi import dan dataset service.
4. Pindahkan locale/formatting helper yang reusable ke `src/ui/formatters.py` bila dipakai halaman lain.
5. Pertahankan ingestion normalization sebagai deterministic pure pipeline.

## Tests

Current coverage utama: `tests/test_loader.py`, `test_normalizer.py`, `test_excel_template_integration.py`, `test_dataset_service.py`, dan `test_readiness.py`.

## Change Contract

Perubahan import, mapping, normalization, replace behavior, dataset version/cache, atau readiness harus meng-update dokumen ini dan test terkait. File upload baru tidak boleh bypass normalization dan repository boundary.