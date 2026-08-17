# Ingestion Architecture

## Purpose

Ingestion mengubah file timesheet eksternal menjadi canonical `TimesheetEntry` yang siap disimpan dan dianalisis.

## Business Flow

```text
bytes + filename
 -> loader
 -> template detection / mapping
 -> header normalization
 -> validation
 -> value normalization
 -> TimesheetEntry list + warnings
 -> repository persistence
```

Dua jalur normalization dipertahankan untuk canonical/manual mapping dan known template format.

## Entry Points and Dependencies

- `src/ingestion/loader.py`: file reader.
- `mapper.py`: template/header mapping.
- `validator.py`: structural validation.
- `normalizer.py`: canonical value conversion dan model creation.
- Dipanggil oleh `ImportService`.
- Output domain: `TimesheetEntry`.

## Current Risks and Non-standard Code

- `normalizer.py` relatif besar karena mendukung beberapa source shape.
- Backward/template compatibility dapat menambah conditional branch yang sulit dihapus tanpa fixture coverage.
- Data contract canonical sebagian masih implicit melalui DataFrame column naming.

## Refactor Recommendations

1. Definisikan canonical input schema dan source-adapter contract secara eksplisit.
2. Split source-specific normalization jika conditional template logic terus tumbuh.
3. Tambahkan fixture untuk setiap supported template/version sebelum refactor.
4. Jangan menambahkan source-specific special case ke page.

## Tests

Current coverage utama: `tests/test_loader.py`, `test_normalizer.py`, `test_excel_template_integration.py`, dan sebagian `test_dataset_service.py`.

## Change Contract

Perubahan supported file type, header mapping, required field, normalization, warning/error policy, atau canonical field wajib meng-update dokumen ini dan fixture-based tests.