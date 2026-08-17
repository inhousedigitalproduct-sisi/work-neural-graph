# Architecture

Dokumen ini menetapkan **target architecture** Work Neural Graph. Ini adalah standar untuk code baru dan refactor; bukan pembenaran untuk seluruh struktur legacy yang masih ada.

## Architecture Principles

1. **Thin Streamlit pages** — `pages/` hanya mengorkestrasi input, state, service call, dan rendering.
2. **Business logic lives outside UI** — kalkulasi analytics, graph, ingestion, quality, dan transformasi data harus berada di `src/`.
3. **One responsibility per module** — hindari service atau page yang sekaligus melakukan persistence, domain calculation, formatting, dan rendering.
4. **Deterministic first** — hasil deterministic harus tersedia tanpa dependency LLM; semantic/LLM adalah enrichment opsional.
5. **Repository boundary for persistence** — SQLite tidak diakses langsung dari page atau analytics.
6. **Explicit contracts** — service dan analyzer menerima/return model atau DataFrame dengan schema yang diketahui.
7. **Performance is a feature** — renderer interaktif harus punya disable switch, bounded work, dan degradation strategy.
8. **Architecture and tests change with code** — production change tanpa architecture screening dan test impact dianggap belum selesai.

## Target Layering

```text
Streamlit Pages / UI
        |
        v
Application Services / Use Cases
        |
        +--------------------+
        v                    v
Domain / Analytics / Graph / Quality
        |                    |
        v                    v
Repositories            External Adapters
        |               (LLM, file readers)
        v
SQLite / Files
```

### Presentation layer

- `app.py`, `pages/`, `src/ui/`.
- Boleh: widget, layout, formatting presentation, session-state orchestration.
- Tidak boleh: graph algorithm, fuzzy matching, normalization, SQL, provider HTTP logic, large embedded JS engines.

### Application/service layer

- Use case seperti import dataset, load active dataset, build collaboration graph snapshot, quality audit orchestration.
- Target: pecah `src/services.py` menjadi service yang fokus (`import_service`, `dataset_service`, dan bila masih diperlukan `graph_service`).
- Service boleh menggabungkan domain components, tetapi tidak mengandung UI rendering.

### Domain/analysis layer

- `src/analytics/`, `src/graph/`, `src/quality/`, `src/domain/`.
- Pure/deterministic functions diprioritaskan agar mudah diuji.
- Data filtering yang dipakai lintas fitur harus memiliki satu implementation canonical.

### Infrastructure/adapters

- `src/database/`, `src/ingestion/`, `src/llm/`, `src/utils/config.py`.
- Secrets hanya dari environment variable; config file tidak menyimpan secret.
- Adapter external tidak boleh mengubah semantic business rule secara diam-diam.

## Dependency Rules

Allowed dependency direction:

```text
pages/ui -> services -> domain/analytics/graph/quality -> repository/adapters
```

Rules:

- `src/analytics` tidak boleh bergantung pada Streamlit.
- `src/graph` renderer tidak boleh mengambil data dari database.
- `src/database` tidak boleh mengimpor page/UI.
- `src/llm` tidak boleh menjadi requirement untuk deterministic analytics.
- Shared filtering harus memiliki satu contract; jangan membuat filter semantics berbeda per halaman tanpa alasan bisnis.
- UI-specific JS/CSS harus berada di renderer/component khusus. Logic neuron impulse yang saat ini di-inject dari `pages/2_Neural_Graph.py` adalah transitional debt dan targetnya dipindahkan ke renderer module.

## Data and State Rules

- Active dataset berasal dari `TimesheetRepository` melalui service boundary.
- Dataset cache harus di-version oleh import hash/timestamp dan di-clear pada mutation.
- Canonical fields minimal: `work_date`, `employee`, `project`, `task_key`, `hours`; optional fields harus dinormalisasi sebelum analytics.
- Streamlit session state tidak boleh menjadi source of truth untuk persisted business data.

## Rendering Rules

- Sigma.js adalah renderer interactive collaboration graph yang aktif.
- Renderer lama tidak boleh dipakai kembali tanpa explicit decision.
- Visual encoding harus menjelaskan arti warna, ukuran, dan edge weight.
- Animation harus opt-in jika berdampak nyata pada CPU/GPU, memiliki bounded edge count/FPS, pause ketika tab hidden, dan menghormati reduced motion.

## Error and Configuration Standard

- Configuration dibaca lewat `src/utils/config.py`.
- Error domain/service dibuat actionable; page hanya menerjemahkan ke pesan user.
- Jangan menelan exception luas tanpa logging dan fallback yang jelas.
- Backward compatibility alias harus diberi alasan dan rencana penghapusan bila sudah tidak diperlukan.

## Change Governance

Untuk setiap production change sebelum commit ke `main`:

1. Screen changed files menggunakan `testing/scripts/screen_change.py`.
2. Update semua `docs/architecture/modules/*.md` yang dipetakan sebagai terdampak.
3. Add/update test di `tests/` yang relevan.
4. Jalankan `testing/scripts/validate_architecture_docs.py`.
5. Jalankan `testing/scripts/run_changed_tests.py` untuk test selection berdasarkan impact map.
6. Commit code + docs + tests sebagai satu perubahan yang dapat ditelusuri.

GitHub Action menjalankan gate yang sama setelah push ke `main`. Karena repository menggunakan direct-to-main workflow, CI adalah safety net; screening lokal/agent sebelum commit tetap merupakan gate utama.

## Testing Standard

- **Unit tests**: pure analysis, mapper, normalizer, quality rule, graph calculation.
- **Integration tests**: import -> repository -> active dataset, filter -> analytics snapshot, collaboration graph result.
- **Renderer contract tests**: payload/HTML invariants yang dapat diuji tanpa browser bila memungkinkan.
- **Regression tests**: setiap bug fix harus mereproduksi bug sebelum fix dan pass setelah fix.
- Folder `tests/` menyimpan pytest test cases.
- Folder `testing/` menyimpan governance, impact mapping, dan runner scripts; jangan membuat duplicate test framework.

## Refactor Priorities

1. Pindahkan neuron impulse injection dari Streamlit page ke renderer/component khusus.
2. Pisahkan `src/services.py` berdasarkan responsibility dan hilangkan konstruksi service berlapis yang tidak perlu.
3. Decouple `AnalyticsService` dari legacy date-graph construction jika KPI hanya membutuhkan filtered dataset/metrics.
4. Audit `src/graph/visualizer.py` dan `collaboration_visualizer.py`; hapus/deprecate renderer yang tidak lagi digunakan setelah usage search dan regression test.
5. Satukan deterministic quality audit orchestration yang saat ini muncul di lebih dari satu page.
6. Pindahkan reusable chart builders/formatters dari page besar ke presentation modules setelah business behavior stabil.