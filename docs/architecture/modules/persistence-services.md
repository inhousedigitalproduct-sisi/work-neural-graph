# Persistence and Services Architecture

## Purpose

Layer ini mengelola SQLite repository, import history, active dataset, cache versioning, dan application services yang menghubungkan ingestion/graph dengan persistence.

## Business Flow

```text
Application service
 -> TimesheetRepository
 -> SQLite

ImportService
 -> ingestion
 -> repository save/replace
 -> cache invalidation

TimesheetDataService
 -> latest import version
 -> cached active dataset
 -> summary/history
```

## Entry Points and Dependencies

- `src/database/sqlite.py`: database initialization/connection support.
- `src/database/repository.py`: persistence API.
- `src/services.py`: `ImportService`, `GraphService`, `TimesheetDataService`.
- `src/domain/models.py`: persisted/domain models.

## Current Risks and Non-standard Code

- `src/services.py` memuat beberapa use case berbeda dalam satu file.
- `TimesheetDataService` membuat `ImportService` untuk memperoleh repository; dependency graph lebih berat dari yang diperlukan.
- `ImportService` mengimpor Streamlit untuk cache invalidation, sehingga application/infrastructure layer terikat UI framework.
- `GraphService` adalah bagian dari legacy date-graph pipeline tetapi masih menjadi dependency `AnalyticsService`.

## Refactor Recommendations

1. Split service classes per file/use case.
2. Inject repository ke service atau construct repository langsung pada composition root.
3. Buat cache adapter/event invalidation agar service tidak mengimpor Streamlit.
4. Review GraphService setelah analytics decoupling; hapus jika tidak ada consumer.
5. Pertahankan transaction/duplicate import semantics di repository dan test integration.

## Tests

Current coverage utama: `tests/test_dataset_service.py`, ingestion integration tests, dan graph/analytics tests yang menggunakan service boundary.

## Change Contract

Perubahan schema database, transaction, duplicate/replace semantics, cache version, service construction, atau active dataset source wajib meng-update dokumen ini dan integration tests.