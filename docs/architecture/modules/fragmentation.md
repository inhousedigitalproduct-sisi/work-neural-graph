# Fragmentation Architecture

## Purpose

Fragmentation Analysis menjelaskan jeda pengerjaan, task continuity, context switching, dan concurrency agar user dapat melihat pola kerja yang terputus atau tersebar.

## Business Flow

```text
Active dataset
 -> shared filters
 -> AnalyticsService.build_snapshot
 -> fragmentation / continuity / context switch / concurrency
 -> KPI summary
 -> Streamlit metrics + Plotly charts + detail tables
```

Business interpretation seperti `Kontinu`, `Cukup kontinu`, `Terputus`, serta pola switching saat ini dibentuk di page untuk presentation.

## Entry Points and Dependencies

- Entry point: `pages/3_Fragmentation.py`.
- Orchestrator: `src/analytics/service.py`.
- Calculators: `fragmentation.py`, `continuity.py`, `context_switch.py`, `concurrency.py`, `kpi.py`.
- Filtering/graph dependency: `src/graph/builder.py` melalui `GraphService`.
- Visualization: Plotly builders di page.
- Shared filters: `src/ui/components.py`.

## Current Risks and Non-standard Code

- Analytics snapshot terikat ke `GraphBuildResult` legacy untuk KPI, membuat fragmentation bergantung pada graph construction walau user hanya memerlukan analytics.
- Banyak Plotly builder dan threshold presentation berada di page yang besar.
- Threshold label continuity/switching belum menjadi centralized business/presentation policy.
- Perubahan analytics function dapat berdampak ke beberapa halaman sekaligus tetapi dependency tidak selalu terlihat dari page.

## Refactor Recommendations

1. Buat analytics snapshot yang menerima filtered DataFrame langsung; graph metric menjadi optional input.
2. Extract chart builders ke `src/ui/analytics_charts.py` jika sudah reusable.
3. Tetapkan threshold interpretation sebagai named constants/policy dengan tests.
4. Pertahankan analyzer sebagai pure functions tanpa Streamlit dependency.

## Tests

Current coverage utama: `tests/test_analytics.py` dan `tests/test_graph_builder.py`.

## Change Contract

Perubahan formula fragmentation, continuity, switching, concurrency, KPI, filter semantics, atau interpretation threshold wajib meng-update dokumen ini dan regression tests dengan dataset kecil yang deterministic.