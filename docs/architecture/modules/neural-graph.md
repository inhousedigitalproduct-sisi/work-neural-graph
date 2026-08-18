# Neural Graph Architecture

## Purpose

Neural Graph adalah network explorer untuk membaca pola kolaborasi antar-karyawan berdasarkan `task_key` yang sama. Runtime mengikuti prinsip **exploration-first**: ringan, node compact, edge mudah dibaca, dan zoom dapat masuk jauh ke cluster padat.

Dua jenis evidence dipisahkan:

1. **Shared-task evidence** — edge undirected berarti dua karyawan berbagi `task_key` pada scope project/date aktif. `shared_task_count` menjadi metric utama untuk warna dan ketebalan garis.
2. **Penyebutan kolaborator pada Note** — pemilik timesheet menyebut karyawan lain secara deterministic. Evidence ini dianalisis sebagai tabel/insight dan tidak dianimasikan pada network.

Penyebutan nama dan connectivity adalah evidence pola kerja/dokumentasi, bukan penilaian performa individu.

## Business Flow

```text
Active dataset
 -> date + Nama Project filter
 -> apply_graph_filters
 -> filtered timesheet rows
      |-> build_collaboration_graph
      |     -> base employee nodes + undirected shared-task edges
      |     -> edge menyimpan shared_task_keys untuk recompute metric
      |
      |-> extract_collaboration_mentions
            -> deterministic employee alias matching on note
            -> row-level source -> target mention evidence
            -> aggregated mention pairs

base shared-task graph
 -> Minimum task bersama
 -> apply_collaboration_threshold
 -> active edges
 -> active/isolated nodes
 -> recomputed node metrics + graph summary
 -> Sigma payload/layout/community/search/detail

thresholded graph
 -> Top Collaborators
 -> Strongest Pairs
 -> Key Connectors (weighted betweenness)
 -> Low Connectivity
 -> Collaboration Clusters

mention evidence
 -> reciprocity / mutual / one-sided / silent / mention-only analysis
 -> table below graph
```

## Entry Points and Dependencies

- Entry point: `pages/2_Neural_Graph.py`.
- Scope filtering: `src/graph/builder.py::GraphFilterConfig/apply_graph_filters`.
- Shared-task graph, threshold recomputation, dan graph insights: `src/graph/collaboration.py`.
- Mention extraction: `src/graph/collaboration_mentions.py`.
- Manual nickname/alias config: `config/employee_aliases.json`.
- Main renderer: `src/graph/sigma_renderer.py`.
- Dataset: `TimesheetDataService`.
- Period analytics: `AnalyticsService`.
- Runtime browser dependencies: Graphology + Sigma.js dari CDN.

## Collaboration Threshold Contract

`Minimum task bersama` adalah filter graph, bukan sekadar filter garis.

Urutan wajib:

```text
scope -> threshold -> active edges -> active nodes -> node metrics
      -> isolated/community -> summary -> search/detail -> renderer/insights
```

Contract:

- Edge dengan `shared_task_count < threshold` tidak masuk graph aktif.
- `collaborator_count`, `collaborative_task_count`, `project_count`, `collaborative_hours`, top collaborators, dan top tasks dihitung ulang dari edge yang lolos threshold.
- `shared_task_keys` disimpan pada edge internal untuk menjaga recomputation tetap berbasis task identity, bukan label task.
- Isolated employees disembunyikan secara default. `Show Isolated` menambahkan kembali employee pada scope yang tidak memiliki edge pada threshold aktif.
- Search hanya menerima node yang benar-benar dikirim ke renderer.
- Summary graph dan detail employee memakai graph hasil threshold yang sama.
- Jika Project/Range Date mengubah maximum `shared_task_count`, state slider harus di-clamp ke range baru agar tidak membawa threshold invalid.
- Period Analysis tetap merupakan analytics scope-level terpisah dan tidak dipaksa mengikuti threshold graph.
- Mention analysis tetap scope-level terpisah karena semantic-nya adalah evidence Note, bukan visual threshold.

## Collaboration Insight Contract

Insight v1 dihitung deterministically tanpa LLM:

- **Top Collaborators** — ranking breadth (`collaborator_count`) lalu shared tasks, collaborative hours, dan project.
- **Strongest Pairs** — pasangan dengan `shared_task_count` tertinggi pada graph aktif.
- **Key Connectors** — weighted betweenness centrality. Edge yang lebih kuat memiliki distance `1 / shared_task_count`, sehingga hubungan kuat dianggap lebih dekat.
- **Low Connectivity** — employee dengan degree rendah/isolated pada scope + threshold aktif. Ini bukan performance score.
- **Collaboration Clusters** — greedy modularity communities berbobot `shared_task_count`, dengan connected-components fallback.

Semua insight graph mengikuti `Minimum task bersama`. Low Connectivity boleh memakai result yang menyertakan isolated employee agar node yang hilang dari graph default tetap dapat diaudit.

## Directional Extraction Contract

- Source selalu nilai `employee` dari row timesheet.
- Target hanya boleh employee lain dari canonical employee roster aktif yang ditemukan di `note`.
- `note` adalah source text v1; `summary` tidak digunakan untuk mention evidence agar semantic tetap eksplisit.
- Matching deterministic: full canonical name `1.00`, manual alias `0.98`, unique two-word alias `0.95`, unique automatic single-token alias `0.92`.
- Threshold default adalah **0.90**.
- Automatic single-token alias diterima mulai **3 karakter** agar nama valid seperti `Ari`, `Eko`, `Adi`, atau `Ayu` tidak false-negative.
- Single-token hanya diterima jika token tersebut dimiliki tepat satu employee pada canonical roster. Alias ambiguous dibuang.
- Automatic token 1-2 karakter tetap ditolak; gunakan canonical full name atau manual alias jika memang diperlukan.
- Self-mention diabaikan.
- Satu target dihitung maksimum satu kali per `entry_id`, walaupun namanya muncul berulang pada Note yang sama.
- Evidence row tetap audit-friendly: source, target, entry id, date, task, project, matched alias, confidence, context, dan note hash.
- Extraction tidak menggunakan LLM.

## Mention Insight Contract

Pair insight menggabungkan shared-task edge scope-level dengan dua arah mention yang mungkin:

- `SHARED_MUTUAL`: shared task ada dan A menyebut B serta B menyebut A.
- `SHARED_ONE_SIDED`: shared task ada tetapi penyebutan hanya satu arah.
- `SHARED_SILENT`: shared task ada tanpa penyebutan nama satu sama lain.
- `MENTION_ONLY`: penyebutan ada tetapi shared task tidak ditemukan pada scope aktif.

Reciprocity:

```text
2 * min(A_to_B, B_to_A) / (A_to_B + B_to_A)
```

Metric ini mengukur balance penyebutan nama pada timesheet, bukan collaboration quality.

## Renderer / Exploration Contract

- Runtime graph tidak memakai animation overlay, canvas particle, pinball, impulse, atau chevron marker.
- Node size default dibatasi sekitar **2.2-5.8 px**.
- Edge membawa semantic frekuensi kolaborasi melalui warna dan ketebalan.
- Spring layout memakai spacing compact adaptif; deep zoom tetap `minCameraRatio = 0.004` dan `maxCameraRatio = 10`.
- Search employee, Fit Graph, Reset View, hover info, click focus, node drag, pan, dan scroll zoom tersedia.
- Isolated visibility dikontrol dari Streamlit (`Show Isolated`) agar summary/search/detail tetap sinkron; tombol renderer lama disembunyikan pada page integration.
- Focus mode tidak boleh membesarkan node secara ekstrem.
- Label muncul adaptif berdasarkan zoom/focus.
- Runtime renderer tidak memiliki `requestAnimationFrame` loop tambahan di luar Sigma.

## Alias Configuration

`config/employee_aliases.json` berisi object canonical employee -> daftar nickname/alias tambahan. Unique canonical single-token matching tidak membutuhkan config; config digunakan untuk nickname tambahan.

## Current Risks and Non-standard Code

- `src/graph/visualizer.py` dan `collaboration_visualizer.py` masih hidup bersama Sigma renderer; perlu usage audit sebelum menghapus renderer legacy.
- Page masih menggunakan `AnalyticsService` untuk Period Analysis yang terpisah dari thresholded collaboration graph.
- Sigma HTML masih berupa large Python f-string berisi CSS/JS, sehingga escaping dan regression risk tetap tinggi.
- CDN availability adalah runtime dependency untuk interactive renderer.
- Note quality dan naming convention menentukan recall mention extraction.

## Refactor Recommendations

1. Pisahkan Sigma payload construction dari HTML template agar renderer dapat diuji lebih granular.
2. Pindahkan isolated visibility sepenuhnya dari legacy JS toolbar ke typed renderer contract pada refactor berikutnya.
3. Decouple period KPI dari legacy date graph builder.
4. Hapus/deprecate renderer yang tidak digunakan setelah repository-wide usage search.
5. Tambahkan browser-level zoom/pan smoke test jika tooling frontend tersedia.

## Tests

Coverage utama: `tests/test_collaboration_graph.py`, `test_graph_builder.py`, `test_graph_visualizer.py`, `test_collaboration_mentions.py`, dan `test_sigma_renderer.py`.

- `test_collaboration_graph.py` menguji shared-task edge, threshold recomputation, isolated visibility, ranking/pair/connector/low-connectivity/cluster insights.
- `test_collaboration_mentions.py` menguji extraction, unique single-token matching mulai 3 karakter, ambiguity rejection, manual alias, diagnostics, reciprocity, dan evidence classification.
- `test_sigma_renderer.py` menguji batas node compact, deep zoom camera range, focus sizing ringan, dan memastikan animation overlay lama tidak kembali.

## Change Contract

Setiap perubahan node/edge semantic, filtering, insight metric, mention extraction, confidence/token threshold, renderer sizing, zoom bounds, focus behavior, visibility, atau performance harus meng-update dokumen ini dan relevant tests. Runtime animation pada graph tidak boleh ditambahkan kembali tanpa evidence user testing bahwa animasi meningkatkan pemahaman.
