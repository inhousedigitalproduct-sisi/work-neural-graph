# Neural Graph Architecture

## Purpose

Neural Graph adalah network explorer untuk membaca pola kolaborasi antar-karyawan berdasarkan `task_key` yang sama. Desain runtime sekarang kembali ke prinsip **exploration-first**: ringan, node compact, edge mudah dibaca, dan zoom dapat masuk jauh ke cluster padat.

Dua jenis evidence tetap dipisahkan:

1. **Shared-task evidence** — edge undirected berarti dua karyawan berbagi `task_key` pada scope project/date aktif. `shared_task_count` menjadi metric utama untuk warna dan ketebalan garis.
2. **Penyebutan kolaborator pada Note** — pemilik timesheet menyebut karyawan lain secara deterministic. Evidence ini tetap dianalisis sebagai tabel/insight, tetapi tidak lagi dianimasikan pada network.

Penyebutan nama adalah evidence pola dokumentasi/koordinasi, bukan penilaian performa individu.

## Business Flow

```text
Active dataset
 -> date + Nama Project filter
 -> apply_graph_filters
 -> filtered timesheet rows
      |-> build_collaboration_graph
      |     -> employee nodes + undirected shared-task edges
      |
      |-> extract_collaboration_mentions
            -> deterministic employee alias matching on note
            -> row-level source -> target mention evidence
            -> aggregated mention pairs

shared-task graph
 -> minimum shared-task threshold
 -> Sigma payload/layout/community
 -> lightweight interactive exploration

mention evidence
 -> reciprocity / mutual / one-sided / silent / mention-only analysis
 -> table below graph
```

## Entry Points and Dependencies

- Entry point: `pages/2_Neural_Graph.py`.
- Filtering contract: `src/graph/builder.py::GraphFilterConfig/apply_graph_filters`.
- Shared-task collaboration model: `src/graph/collaboration.py`.
- Mention extraction: `src/graph/collaboration_mentions.py`.
- Manual nickname/alias config: `config/employee_aliases.json`.
- Main renderer: `src/graph/sigma_renderer.py`.
- Dataset: `TimesheetDataService`.
- Analytics summary: `AnalyticsService`.
- Runtime browser dependencies: Graphology + Sigma.js dari CDN.

## Directional Extraction Contract

- Source selalu nilai `employee` dari row timesheet.
- Target hanya boleh employee lain dari canonical employee roster aktif yang ditemukan di `note`.
- `note` adalah source text v1; `summary` tidak digunakan untuk mention evidence agar semantic tetap eksplisit.
- Matching deterministic: full canonical name `1.00`, manual alias `0.98`, unique two-word alias `0.95`, unique automatic single-token alias `0.92`.
- Threshold default adalah **0.90**. Single-token name hanya boleh menghasilkan evidence jika token tersebut dimiliki tepat satu employee pada canonical roster.
- Alias yang dimiliki lebih dari satu employee dianggap ambiguous dan dibuang.
- Self-mention diabaikan.
- Satu target dihitung maksimum satu kali per `entry_id`, walaupun namanya muncul berulang pada Note yang sama.
- Evidence row tetap audit-friendly: source, target, entry id, date, task, project, matched alias, confidence, context, dan note hash.
- Extraction tidak menggunakan LLM.

## Mention Insight Contract

Pair insight menggabungkan shared-task edge dengan dua arah mention yang mungkin:

- `SHARED_MUTUAL`: shared task ada dan A menyebut B serta B menyebut A.
- `SHARED_ONE_SIDED`: shared task ada tetapi penyebutan hanya satu arah.
- `SHARED_SILENT`: shared task ada tanpa penyebutan nama satu sama lain.
- `MENTION_ONLY`: penyebutan ada tetapi shared task tidak ditemukan pada scope aktif.

Reciprocity dihitung sebagai:

```text
2 * min(A_to_B, B_to_A) / (A_to_B + B_to_A)
```

Metric ini mengukur balance penyebutan nama pada timesheet, bukan collaboration quality.

## Renderer / Exploration Contract

- Runtime graph **tidak memakai animation overlay, canvas particle, pinball, impulse, atau chevron marker**.
- Node size default dibatasi pada kisaran sekitar **2.2-5.8 px** agar node tidak menutupi jaringan.
- Edge tetap membawa semantic frekuensi kolaborasi melalui warna dan ketebalan.
- Layout sedikit lebih renggang agar edge crossing dan cluster lebih mudah dibaca.
- Sigma camera harus mendukung zoom-in jauh; `minCameraRatio` ditetapkan **0.004** dan `maxCameraRatio` **10**.
- Search employee, Fit Graph, Hide Isolated, Reset View, hover info, click focus, node drag, pan, dan scroll zoom tetap tersedia.
- Focus mode tidak boleh membesarkan node secara ekstrem. Node lain cukup diredupkan ringan dan edge yang terkait focus hanya ditegaskan secukupnya.
- Detail panel dibuat lebih compact daripada versi sebelumnya agar viewport graph menjadi area utama eksplorasi.
- Label muncul adaptif berdasarkan zoom/focus dan tidak boleh menguasai dense graph.
- Runtime renderer tidak memiliki `requestAnimationFrame` loop tambahan di luar Sigma.

## Alias Configuration

`config/employee_aliases.json` berisi object canonical employee -> daftar nickname/alias tambahan.

Contoh:

```json
{
  "Muhammad Andras Syahrindra Ramadhani": ["Andras", "Mas Andras"],
  "Vitta Kusmala": ["Vitta", "Mbak Vitta"]
}
```

Config baseline boleh kosong (`{}`). Unique canonical single-token matching tidak membutuhkan config; config digunakan untuk nickname tambahan.

## Current Risks and Non-standard Code

- `src/graph/visualizer.py` dan `collaboration_visualizer.py` masih hidup bersama Sigma renderer; perlu usage audit sebelum menghapus renderer legacy.
- Page menggunakan `AnalyticsService` yang masih membangun legacy `GraphService/GraphBuilder` untuk analytics snapshot.
- Sigma HTML masih berupa large Python f-string berisi CSS/JS, sehingga escaping dan regression risk tetap tinggi.
- CDN availability adalah runtime dependency untuk interactive renderer.
- Note quality dan naming convention menentukan recall mention extraction.

## Refactor Recommendations

1. Pisahkan Sigma payload construction dari HTML template agar renderer dapat diuji lebih granular.
2. Decouple period KPI dari legacy date graph builder.
3. Hapus/deprecate renderer yang tidak digunakan setelah repository-wide usage search.
4. Tambahkan browser-level zoom/pan smoke test jika tooling frontend tersedia.
5. Jika mention extraction sudah stabil, evaluasi enrichment jenis interaksi (review/support/handover/coordination) sebagai layer analitik terpisah.

## Tests

Coverage utama: `tests/test_collaboration_graph.py`, `test_graph_builder.py`, `test_graph_visualizer.py`, `test_collaboration_mentions.py`, dan `test_sigma_renderer.py`.

- `test_collaboration_mentions.py` menguji extraction, unique single-token matching, ambiguity rejection, manual alias, reciprocity, dan evidence classification.
- `test_sigma_renderer.py` menguji batas node compact, deep zoom camera range, focus sizing yang ringan, dan memastikan animation overlay lama tidak kembali masuk ke renderer.

## Change Contract

Setiap perubahan node/edge semantic, filtering, mention extraction, confidence threshold, renderer sizing, zoom bounds, focus behavior, visibility, atau performance harus meng-update dokumen ini dan relevant tests. Runtime animation pada graph tidak boleh ditambahkan kembali tanpa evidence dari user testing bahwa animasi tersebut benar-benar meningkatkan pemahaman.
