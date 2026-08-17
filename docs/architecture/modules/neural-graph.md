# Neural Graph Architecture

## Purpose

Neural Graph memvisualisasikan dua jenis evidence kolaborasi yang sengaja dipisahkan:

1. **Shared-task evidence** — edge undirected berarti dua karyawan berbagi `task_key` pada scope project/date aktif. `shared_task_count` tetap menjadi metric frekuensi kolaborasi utama untuk warna dan ketebalan garis.
2. **Directional acknowledgement evidence** — marker chevron satu arah berarti pemilik timesheet menyebut karyawan lain pada kolom `note` dengan deterministic employee-name matching.

Acknowledgement adalah evidence pola dokumentasi/koordinasi, bukan penilaian performa individu.

## Business Flow

```text
Active dataset
 -> date + Nama Project filter
 -> apply_graph_filters
 -> filtered timesheet rows
      |-> build_collaboration_graph
      |     -> shared-task employee nodes + undirected edges
      |
      |-> extract_collaboration_mentions
            -> deterministic employee alias matching on note
            -> row-level directional evidence
            -> aggregated source -> target acknowledgement

shared edges + directional evidence
 -> acknowledgement insight classification / reciprocity
 -> threshold minimum shared tasks
 -> Sigma payload/layout/community
 -> one-way directional chevron overlay on visible shared-task edges
```

## Entry Points and Dependencies

- Entry point: `pages/2_Neural_Graph.py`.
- Filtering contract: `src/graph/builder.py::GraphFilterConfig/apply_graph_filters`.
- Shared-task collaboration model: `src/graph/collaboration.py`.
- Directional extraction: `src/graph/collaboration_mentions.py`.
- Manual nickname/alias config: `config/employee_aliases.json`.
- Main renderer: `src/graph/sigma_renderer.py`.
- Lightweight directional animation helper: `src/graph/pinball_animation.py`.
- Dataset: `TimesheetDataService`.
- Analytics summary: `AnalyticsService`.
- Runtime browser dependencies: Graphology + Sigma.js dari CDN.

## Directional Extraction Contract

- Source selalu nilai `employee` dari row timesheet.
- Target hanya boleh employee lain dari canonical employee roster aktif yang ditemukan di `note`.
- `note` adalah source text v1; `summary` tidak digunakan untuk directional acknowledgement agar semantic tetap eksplisit.
- Matching deterministic: full canonical name `1.00`, manual alias `0.98`, unique two-word alias `0.95`, unique automatic single-token alias `0.92`.
- Threshold default adalah **0.90**. Single-token name boleh menghasilkan evidence hanya jika token tersebut dimiliki tepat satu employee pada canonical roster. Jika token yang sama dimiliki lebih dari satu employee, alias dianggap ambiguous dan dibuang.
- Manual alias tetap digunakan untuk nickname yang tidak berasal dari token canonical employee name.
- Self-mention diabaikan.
- Satu target dihitung maksimum satu kali per `entry_id`, walaupun nama target muncul berulang di Note yang sama.
- Evidence row menyimpan source, target, entry id, date, task, project, matched alias, confidence, context pendek, dan note hash agar hasil dapat diaudit.
- Extraction tidak menggunakan LLM. LLM dapat menjadi enrichment terpisah di masa depan untuk mengklasifikasikan jenis interaksi, bukan menentukan identitas employee.

## Extraction Diagnostics Contract

UI menampilkan counter ringan untuk membantu membedakan masalah extraction dengan masalah renderer:

- `notes_scanned`: jumlah Note non-empty pada scope aktif.
- `notes_with_accepted_evidence`: jumlah timesheet entry yang menghasilkan minimal satu target valid.
- `notes_without_accepted_evidence`: Note non-empty yang tidak menghasilkan target valid; ini dapat berarti Note tidak menyebut employee lain atau candidate name tidak lolos matching.
- `accepted_evidence`: jumlah source-target evidence setelah dedupe per entry.
- `directional_pairs`: jumlah arah acknowledgement teragregasi.
- `visible_signals`: jumlah directional signal yang juga memiliki shared-task edge pada graph yang sedang tampil.

Jika shared-task edge ada tetapi `visible_signals = 0`, investigasi dilakukan pada Note/matching/visible-edge join sebelum mengubah canvas renderer.

## Acknowledgement Insight Contract

Pair insight menggabungkan shared-task edge dengan dua kemungkinan arah acknowledgement:

- `SHARED_MUTUAL`: shared task ada dan A -> B serta B -> A sama-sama terdeteksi.
- `SHARED_ONE_SIDED`: shared task ada tetapi acknowledgement hanya satu arah.
- `SHARED_SILENT`: shared task ada tanpa acknowledgement pada Note.
- `MENTION_ONLY`: acknowledgement ada tetapi shared task tidak ditemukan pada scope aktif.

Acknowledgement reciprocity dihitung sebagai:

```text
2 * min(A_to_B, B_to_A) / (A_to_B + B_to_A)
```

Nilai ini mengukur balance acknowledgement pada timesheet, bukan collaboration quality. Asimetri dapat normal karena role coordinator, reviewer, lead, task owner, support, atau pola dokumentasi yang berbeda.

## Animation Contract

- Marker hanya berasal dari **directional acknowledgement evidence**, bukan dari urutan alfabet edge atau asumsi bahwa shared-task selalu reciprocal.
- Marker berbentuk **chevron/arrowhead** sehingga arah dapat dibaca dari satu frame tanpa harus menunggu gerak dot.
- Marker bergerak satu arah dari source ke target, lalu restart dari source. Tidak memantul kembali.
- Orientasi marker dihitung dari vektor source-target (`atan2`) dan selalu menunjuk ke target.
- Jika A -> B dan B -> A sama-sama punya evidence, dua signal terpisah dapat bergerak berlawanan pada edge yang sama.
- Shared-task edge tanpa directional evidence tetap tampil tetapi tanpa marker.
- `MENTION_ONLY` tetap tersedia pada analysis table tetapi belum dirender sebagai edge, agar semantic garis tetap konsisten sebagai shared task.
- Saat tidak ada focus, marker memakai warna edge dengan opacity tinggi dan outline putih tipis agar terbaca di background gelap.
- Saat hover/klik node, marker pada relasi node aktif diperbesar dan diperjelas; marker lain diredupkan agar active path lebih mudah dibaca tanpa menambah glow berat.
- Tidak memakai streak, gradient, large shadow blur, atau additive glow yang mahal.
- Maksimum **120 directional signals** dianimasikan, diprioritaskan berdasarkan jumlah timesheet evidence.
- Frame interval adaptif berdasarkan jumlah signal yang dianimasikan.
- Posisi viewport node di-cache sekali per frame.
- Koordinat viewport harus divalidasi (`Number.isFinite`) agar satu signal invalid tidak mematikan animation loop secara diam-diam.
- Rendering berhenti saat tab browser hidden dan dihormati saat `prefers-reduced-motion` aktif.

## Alias Configuration

`config/employee_aliases.json` berisi object canonical employee -> daftar nickname/alias yang dianggap eksplisit.

Contoh:

```json
{
  "Muhammad Andras Syahrindra Ramadhani": ["Andras", "Mas Andras"],
  "Vitta Kusmala": ["Vitta", "Mbak Vitta"]
}
```

Config baseline boleh kosong (`{}`). Unique canonical single-token matching tidak membutuhkan config; config digunakan untuk nickname tambahan. Alias yang ambiguous terhadap employee lain tetap tidak boleh menghasilkan evidence.

## Current Risks and Non-standard Code

- `src/graph/visualizer.py` dan `collaboration_visualizer.py` masih hidup bersama Sigma renderer; perlu usage audit agar renderer legacy tidak kembali dipakai tanpa sengaja.
- Page menggunakan `AnalyticsService` yang saat ini membangun legacy `GraphService/GraphBuilder` untuk analytics snapshot, walaupun visual graph sudah collaboration-based.
- Sigma HTML adalah large Python f-string berisi CSS/JS, sehingga raw string escaping dan regression risk tinggi.
- Nama helper/file `pinball_animation.py` adalah legacy naming; semantic visual sekarang directional chevron, sehingga rename dapat dilakukan nanti sebagai refactor terpisah agar perubahan visual ini tetap kecil dan mudah direview.
- CDN availability adalah runtime dependency untuk interactive renderer.
- Note quality dan naming convention menentukan recall extraction. Unique-token matching meningkatkan recall, tetapi ambiguity gate tetap wajib untuk menahan false-positive.

## Refactor Recommendations

1. Pertahankan extraction dan animation concern pada helper khusus, bukan di Streamlit page.
2. Rename `pinball_animation.py` ke nama yang merepresentasikan directional marker setelah import/reference migration dapat dilakukan atomik.
3. Pisahkan Sigma payload construction dari HTML template agar dapat unit-test secara langsung.
4. Decouple period KPI dari legacy date graph builder.
5. Hapus/deprecate renderer yang tidak digunakan setelah repository-wide usage search.
6. Tambahkan browser-level performance smoke test jika tooling frontend tersedia.
7. Jika directional extraction sudah stabil, evaluasi enrichment jenis interaksi (review/support/handover/coordination) sebagai layer terpisah.

## Tests

Coverage utama: `tests/test_collaboration_graph.py`, `test_graph_builder.py`, `test_graph_visualizer.py`, `test_collaboration_mentions.py`, dan `test_pinball_animation.py`.

- `test_collaboration_mentions.py` menguji one-way extraction, dedupe per entry, unique single-token matching, ambiguous-token rejection, manual nickname alias, extraction diagnostics, mutual/one-sided/silent/mention-only classification, reciprocity, dan filtering signal ke visible shared edge.
- `test_pinball_animation.py` memastikan animation menerima explicit directional signals, bergerak one-way, memakai chevron yang dirotasi ke target, tidak lagi menggambar circle marker, meredupkan marker non-focus, tetap bounded, tanpa heavy gradient/shadow effect, menghormati reduced-motion, dan memiliki invalid viewport coordinate guard.

## Change Contract

Setiap perubahan node/edge semantic, filtering, extraction rule, confidence threshold, alias handling, diagnostics, reciprocity metric, renderer encoding, directional animation, visibility, atau performance limit harus meng-update dokumen ini dan relevant tests. Directional evidence harus explainable dari timesheet row; jangan mengubah arah signal berdasarkan heuristic visual yang tidak memiliki evidence data.
