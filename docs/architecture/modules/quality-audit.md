# Quality Audit Architecture

## Purpose

Quality Audit menilai kualitas entry timesheet dengan deterministic checks terlebih dahulu: copy/near-copy, kualitas note, overlap, duration issue, repeated/long activity, dan overall effectiveness. Semantic similarity/topic analysis adalah enrichment opsional.

## Business Flow

```text
Active dataset
 -> shared filters
 -> prepare_quality_dataframe
 -> deterministic audit
    -> duration issues
    -> exact/near-copy
    -> overlap
    -> managerial summary/KPI
 -> trend and issue visualization
 -> optional semantic embedding/topic grouping
```

Deterministic results harus tetap dapat digunakan walau embedding/LLM provider tidak tersedia.

## Entry Points and Dependencies

- Entry point: `pages/5_Quality_Audit.py`.
- Core quality rules: `src/quality/timesheet_quality.py`.
- Dataset readiness: `src/quality/readiness.py`.
- Dataset access: `TimesheetDataService`.
- Filter: `apply_graph_filters` / shared filter component.
- Semantic helpers saat ini juga berada di `timesheet_quality.py`.
- Visualization: Plotly builders di page.

## Current Risks and Non-standard Code

- Deterministic audit orchestration (`prepare -> duration -> copies -> overlap -> managerial_summary`) diduplikasi antara Load Data dan Quality Audit.
- `timesheet_quality.py` besar dan mencampur deterministic rule, semantic vector helper, clustering, serta summary.
- Quality trend menghitung ulang fuzzy matching per period; pada dataset besar dapat mahal.
- Page berisi banyak chart-builder dan state/cache logic.

## Refactor Recommendations

1. Buat `QualityAuditService` atau pure `run_deterministic_audit` reusable.
2. Split deterministic rules dari semantic/vector functions.
3. Tambahkan performance guard/caching untuk trend fuzzy computation.
4. Pisahkan presentation charts setelah contract metric stabil.
5. Pertahankan semantic analysis sebagai explicit user action, bukan prerequisite page load.

## Tests

Current coverage utama: `tests/test_quality.py`, `test_readiness.py`, serta LLM/semantic-related tests bila path semantic digunakan.

## Change Contract

Perubahan threshold, definition issue, KPI score, fuzzy/semantic logic, trend grouping, atau deterministic-vs-semantic execution order wajib meng-update dokumen ini dan test dengan expected metric yang eksplisit.