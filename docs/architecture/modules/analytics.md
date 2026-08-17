# Analytics Core Architecture

## Purpose

Analytics core menyediakan snapshot lintas fitur berisi fragmentation, continuity, context switching, concurrency, graph result, dan KPI pada scope filter yang sama.

## Business Flow

```text
GraphFilterConfig
 -> GraphService.build_graph
 -> filtered dataframe
 -> analyze_fragmentation
 -> analyze_continuity
 -> analyze_context_switching
 -> analyze_concurrency
 -> calculate_kpi_summary
 -> AnalyticsSnapshot
```

## Entry Points and Dependencies

- `src/analytics/service.py` adalah orchestrator.
- Analyzer berada di `src/analytics/*.py`.
- Bergantung pada `GraphService`, `GraphFilterConfig`, `GraphBuildResult`, dan `GraphStrategy`.
- Digunakan terutama oleh Neural Graph period summary dan Fragmentation page.

## Current Risks and Non-standard Code

- Filtering dan analytics terikat ke legacy graph build: `AnalyticsService -> GraphService -> GraphBuilder`.
- `AnalyticsSnapshot` selalu membawa `graph_result` walau consumer tidak selalu membutuhkannya.
- `GraphService` mengonstruksi `ImportService` dan `TimesheetDataService`, memperbesar dependency chain.

## Refactor Recommendations

1. Pisahkan `DatasetFilterService`/pure filtering dari graph construction.
2. Buat analytics snapshot dari filtered DataFrame; graph result optional atau dihitung oleh feature yang membutuhkannya.
3. Pertahankan analyzer pure dan dataclass snapshot immutable bila memungkinkan.
4. Dokumentasikan formula KPI di code/doc ketika threshold atau weighting berubah.

## Tests

Current coverage utama: `tests/test_analytics.py` dan sebagian `tests/test_graph_builder.py`.

## Change Contract

Perubahan schema `AnalyticsSnapshot`, formula analyzer/KPI, filter source, atau dependency ke graph wajib meng-update dokumen ini dan seluruh test consumer terkait.