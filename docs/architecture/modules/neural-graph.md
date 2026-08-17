# Neural Graph Architecture

## Purpose

Neural Graph memvisualisasikan kolaborasi antar-karyawan. Node adalah karyawan; edge berarti dua karyawan berbagi `task_key` pada scope project/date aktif. `shared_task_count` adalah metric frekuensi kolaborasi utama.

## Business Flow

```text
Active dataset
 -> date + Nama Project filter
 -> apply_graph_filters
 -> build_collaboration_graph
 -> employee nodes + shared-task edges
 -> threshold minimum shared tasks
 -> Sigma payload/layout/community
 -> interactive Sigma.js renderer
 -> optional Interactive neuron impulse overlay
```

Node size dapat menggunakan collaborator count, collaborative task count, collaborative hours, atau project count. Edge color/thickness menggunakan jumlah task bersama. Interactive impulse adalah visual aid dan tidak mengubah semantic data.

## Entry Points and Dependencies

- Entry point: `pages/2_Neural_Graph.py`.
- Filtering contract: `src/graph/builder.py::GraphFilterConfig/apply_graph_filters`.
- Collaboration model: `src/graph/collaboration.py`.
- Main renderer: `src/graph/sigma_renderer.py`.
- Dataset: `TimesheetDataService`.
- Analytics summary: `AnalyticsService`.
- Runtime browser dependencies: Graphology + Sigma.js dari CDN.

## Current Risks and Non-standard Code

- Neuron impulse CSS/JavaScript di-inject dari Streamlit page ke HTML renderer; presentation concern tersebar di dua layer.
- `src/graph/visualizer.py` dan `collaboration_visualizer.py` masih hidup bersama Sigma renderer; perlu usage audit agar renderer legacy tidak kembali dipakai tanpa sengaja.
- Page menggunakan `AnalyticsService` yang saat ini membangun legacy `GraphService/GraphBuilder` untuk analytics snapshot, walaupun visual graph sudah collaboration-based.
- Sigma HTML adalah large Python f-string berisi CSS/JS, sehingga raw string escaping dan regression risk tinggi.
- CDN availability adalah runtime dependency untuk interactive renderer.

## Refactor Recommendations

1. Pindahkan Interactive impulse menjadi capability di `sigma_renderer.py` atau dedicated `sigma_interactions.py` dengan parameter `interactive`.
2. Pisahkan payload construction dari HTML template agar dapat unit-test secara langsung.
3. Decouple period KPI dari legacy date graph builder.
4. Hapus/deprecate renderer yang tidak digunakan setelah repository-wide usage search.
5. Tambahkan renderer contract tests untuk legend scale, interactive disabled path, bounded animation settings, dan payload edge metric.

## Tests

Current coverage utama: `tests/test_collaboration_graph.py`, `test_graph_builder.py`, dan `test_graph_visualizer.py`. Coverage browser-level Sigma/interactions masih terbatas.

## Change Contract

Setiap perubahan node/edge semantic, filtering, collaboration metric, renderer encoding, interaction, animation, atau performance limit harus meng-update dokumen ini. Behavior visual baru harus tetap opt-in bila menambah CPU/GPU cost dan harus memiliki regression test yang dapat dijalankan tanpa manual inspection sejauh mungkin.