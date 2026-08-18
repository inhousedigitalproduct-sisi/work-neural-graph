# Neural Graph Architecture

## Purpose

Neural Graph adalah network explorer untuk membaca **evidence kolaborasi yang eksplisit pada Note timesheet**. Relasi tidak lagi dibentuk hanya karena dua employee memiliki `task_key` yang sama.

Semantic utama:

1. **Node** = employee.
2. **Edge** = pemilik timesheet menyebut employee lain pada `note` dan mention lolos deterministic matching.
3. **Task / Project / Hours** = context dari evidence Note, bukan pembentuk edge.
4. Tidak adanya edge berarti **tidak ditemukan evidence penyebutan kolaborator pada Note**, bukan bukti bahwa employee tidak berkolaborasi.

## Business Flow

```text
Active dataset
 -> Project + Range Date scope
 -> apply_graph_filters
 -> filtered timesheet rows
 -> extract_collaboration_mentions
      -> deterministic employee-name matching pada Note
      -> source employee -> target employee evidence per entry
 -> build_note_collaboration_graph
      -> aggregate pair A/B
      -> total Note evidence
      -> A -> B count / B -> A count
      -> task/project/hour context
 -> Minimum evidence Note
 -> active edges + active nodes
 -> recomputed metrics / community / insights
 -> Sigma renderer
```

## Entry Points

- Page: `pages/2_Neural_Graph.py`
- Scope filter: `src/graph/builder.py`
- Mention extraction: `src/graph/collaboration_mentions.py`
- Note-based graph builder: `src/graph/note_collaboration.py`
- Shared graph insight utilities: `src/graph/collaboration.py`
- Renderer: `src/graph/sigma_renderer.py`
- Optional aliases: `config/employee_aliases.json`

## Note Evidence Contract

- Source selalu `employee` pemilik row timesheet.
- Target adalah employee lain yang disebut pada `note`.
- Full canonical name confidence `1.00`.
- Manual alias confidence `0.98`.
- Unique two-word alias confidence `0.95`.
- Unique automatic single-token alias confidence `0.92` mulai 3 karakter.
- Alias ambiguous dibuang.
- Self mention diabaikan.
- Target yang sama dihitung maksimum satu kali per `entry_id`.
- Evidence tetap audit-friendly: source, target, entry id, date, task key, project, alias, confidence, context, note hash.

## Pair Aggregation Contract

Untuk setiap pasangan employee A/B:

- `evidence_count` = total accepted Note evidence pada kedua arah.
- `A -> B` dan `B -> A` tetap disimpan terpisah untuk membaca one-sided/mutual documentation pattern.
- Task, Project, dan Hours hanya menjadi context dari entry evidence.
- Compatibility field `shared_task_count` pada graph utility lama sementara menyimpan `evidence_count`; UI tidak boleh menyebutnya shared task.

## Threshold Contract

`Minimum evidence Note` memfilter pair berdasarkan evidence count dan kemudian menghitung ulang:

- active edges
- active nodes
- collaborator count
- Note evidence count per node
- project/hour context
- isolated status
- community
- search/detail
- graph summary
- Top Collaborators
- Strongest Pairs
- Key Connectors
- Low Connectivity
- Clusters

`Show Isolated` menambahkan kembali employee dalam scope yang tidak memiliki edge pada threshold aktif.

## Renderer Contract

- Node compact, spring layout adaptif, dan deep zoom tetap dipertahankan.
- `minCameraRatio = 0.004`, `maxCameraRatio = 10`.
- Employee search adalah **focus/navigation**, bukan filter yang menghapus graph.
- Employee search memakai **case-insensitive contains matching** terhadap seluruh nama, sehingga potongan nama depan, tengah, atau belakang dapat digunakan.
- Search menampilkan maksimum 20 hasil yang cocok dan Enter memilih hasil pertama.
- Search wajib menggunakan `renderer.getNodeDisplayData(node)` sebelum `camera.animate(...)`; raw NetworkX `x/y` tidak boleh dipakai untuk camera focus.
- Employee terpilih dan neighbor langsung ditegaskan; node lain diredupkan.
- Fit Graph / Reset View mengembalikan overview.
- Embedded JavaScript di Python f-string tidak boleh memakai invalid Python escape sequence. Untuk regex sederhana, gunakan character class seperti `[(]`, `[)]`, `[0-9]` atau escaping Python yang eksplisit.
- Tidak ada impulse/pinball/chevron animation overlay.

## Insight Contract

Semua insight graph berasal dari Note-based graph:

- **Top Collaborators**: breadth relasi, lalu evidence count dan context.
- **Strongest Pairs**: pair dengan evidence Note terbanyak.
- **Key Connectors**: weighted betweenness centrality; evidence lebih kuat dianggap lebih dekat.
- **Low Connectivity**: sedikit/tidak ada evidence connectivity, bukan performance score.
- **Clusters**: community pada graph evidence Note.

## Tests

Coverage utama:

- `tests/test_collaboration_mentions.py`
- `tests/test_note_collaboration.py`
- `tests/test_sigma_renderer.py`
- test graph/analytics lain tetap dijalankan melalui architecture governance sesuai impact mapping.

Regression wajib:

1. employee yang hanya berbagi task tanpa mention Note tidak otomatis mendapat edge Note-based;
2. mention Note dapat membuat edge meskipun task berbeda;
3. threshold evidence rebuild node/summary secara konsisten;
4. employee search memakai Sigma display coordinates sehingga graph tidak hilang saat focus;
5. employee search harus mendukung case-insensitive contains matching, bukan hanya full-name/prefix selection;
6. source `sigma_renderer.py` harus compile tanpa `SyntaxWarning` / `DeprecationWarning` akibat invalid escape sequence.

## Change Contract

Setiap perubahan semantic evidence, matching, threshold, graph weight, node metric, camera focus, insight, atau visibility harus meng-update dokumen ini dan relevant tests. Shared-task collaboration tidak boleh kembali menjadi semantic utama tanpa requirement/user validation baru.
