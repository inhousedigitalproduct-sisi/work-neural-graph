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
 -> lightweight bidirectional pinball-dot overlay
```

Node size dapat menggunakan collaborator count, collaborative task count, collaborative hours, atau project count. Edge color/thickness menggunakan jumlah task bersama. Dot animation adalah visual aid dan tidak mengubah semantic data.

## Entry Points and Dependencies

- Entry point: `pages/2_Neural_Graph.py`.
- Filtering contract: `src/graph/builder.py::GraphFilterConfig/apply_graph_filters`.
- Collaboration model: `src/graph/collaboration.py`.
- Main renderer: `src/graph/sigma_renderer.py`.
- Lightweight animation helper: `src/graph/pinball_animation.py`.
- Dataset: `TimesheetDataService`.
- Analytics summary: `AnalyticsService`.
- Runtime browser dependencies: Graphology + Sigma.js dari CDN.

## Animation Contract

- Animasi default berupa satu dot kecil yang bergerak **bolak-balik** pada edge, untuk merepresentasikan kolaborasi dua arah.
- Tidak memakai streak, gradient, large shadow blur, atau additive glow yang mahal.
- Maksimum **120 edge** dianimasikan; edge diprioritaskan berdasarkan `shared_task_count` tertinggi.
- Frame interval adaptif berdasarkan jumlah edge yang dianimasikan.
- Posisi viewport node di-cache sekali per frame.
- Rendering berhenti saat tab browser hidden dan dihormati saat `prefers-reduced-motion` aktif.
- Hover/focus node hanya menambah highlight ringan pada dot terkait; tidak menambah full-edge glow.

## Current Risks and Non-standard Code

- `src/graph/visualizer.py` dan `collaboration_visualizer.py` masih hidup bersama Sigma renderer; perlu usage audit agar renderer legacy tidak kembali dipakai tanpa sengaja.
- Page menggunakan `AnalyticsService` yang saat ini membangun legacy `GraphService/GraphBuilder` untuk analytics snapshot, walaupun visual graph sudah collaboration-based.
- Sigma HTML adalah large Python f-string berisi CSS/JS, sehingga raw string escaping dan regression risk tinggi.
- CDN availability adalah runtime dependency untuk interactive renderer.

## Refactor Recommendations

1. Pertahankan animation concern di helper khusus, bukan di Streamlit page.
2. Pisahkan payload construction dari HTML template agar dapat unit-test secara langsung.
3. Decouple period KPI dari legacy date graph builder.
4. Hapus/deprecate renderer yang tidak digunakan setelah repository-wide usage search.
5. Tambahkan browser-level performance smoke test jika tooling frontend tersedia.

## Tests

Coverage utama: `tests/test_collaboration_graph.py`, `test_graph_builder.py`, `test_graph_visualizer.py`, dan `test_pinball_animation.py`. `test_pinball_animation.py` memastikan animation bounded, bidirectional, tanpa heavy gradient/shadow effect, dan pause behavior tetap ada.

## Change Contract

Setiap perubahan node/edge semantic, filtering, collaboration metric, renderer encoding, interaction, animation, atau performance limit harus meng-update dokumen ini. Efek visual default wajib bounded dan memiliki regression test yang dapat dijalankan tanpa manual inspection sejauh mungkin.
