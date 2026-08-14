# UI/UX update — 13 August 2026

## Neural Graph

- Added an always-visible "Cara membaca grafik" guide.
- Reworded graph hover content and colour-scale labels in Indonesian.
- Added an explicit explanation of node size and edge thickness.

## Fragmentation Analysis

- Added a plain-language guide for fragmentation, interruption days, and continuity.
- Added a filter-aware executive summary, priority tasks, findings, and recommendations.
- Kept the output deterministic; recommendations are based on the selected dataset/filter.

## AI Analyst

- Redesigned as a local managerial-analysis workflow.
- Added transparent five-step processing status.
- Added deterministic managerial summary, recommendations, and detail tabs.
- Kept Qwen optional: it explains an entered question when available, but never calculates the metrics.

## Audit Kualitas Timesheet

- Added a new page that uses the active dataset and the shared filters; it does not require a second upload.
- Added exact/near-copy, Note quality, repeated activity, duration, and overlap checks.
- Added optional local embedding analysis with topic grouping and semantic relations.
- Added a managerial summary, recommendations, detail tabs, and an Excel export.

# Revision — Management readability & audit evidence

## Neural Graph

- Upgraded Qwen interpretation prompts for executive-level summaries, management attention points, and verification questions.
- Node hover now shows full dates, active employees, related dates, related task names, and up to six detailed activity entries including Note and hours.
- Edge hover now explains why two dates are connected and shows the exact shared tasks behind the relationship.
- Added a cross-year regression test to ensure Sequential relationships remain based on adjacent occurrences of the same task across month/year boundaries.

## Fragmentation Analysis

- Added an explanation of an ideal/traceable task pattern plus a concrete example.
- Added detailed help for fragmentation metrics and the Fragmentation Table.
- Changed Task Timeline to a dark background with white data/labels for higher contrast.
- Reframed recommendations as management discussion points rather than individual performance judgement.

## AI Analyst

- Removed Context Switching from the user-facing summary and tabs; the metric can remain available in backend analytics.
- Added help for Task Prioritas and Per Anggota.
- Clarified employee-table column labels and interpretation boundaries.
- Added filter-signature validation so stale recommendations are not shown after filters change.

## Audit Kualitas

- Added hover help to managerial KPI metrics, including a clear explanation of overlap.
- Added one-call Qwen managerial recommendation generation using only deterministic Python audit outputs.
- Clarified Per Anggota column titles and the meaning of Note minim.
- Copy-paste findings now include both dates, activities, Notes, hours, similarity type, and score.
- Overlap findings now include both activities, start/finish times, Notes, and overlap minutes, plus reading help.
- Duration tab is hidden when no duration finding exists.
- Semantic relations now include both full activity/Note records and a readable closeness label.
- Topic groups now include a representative activity theme, counts, hours, related employees/projects, and an example Note; group numbers are explicitly described as cluster IDs, not rankings.
- Added scope/signature validation so audit results must be rerun when filters or audit thresholds change.

## 2026-08-13 — Load Data redesign

- Redesigned **Load Data** into **Load & Validate Timesheet** as a dataset-readiness gateway.
- Added upload card with active-dataset status and safer default Replace behavior.
- Added high-level KPI cards: entries, employees, projects, hours, and dataset period.
- Added deterministic **Data Readiness** checks for required structure, work dates, essential values, Note quality signal, overlap signal, and Actual Start–Finish coverage.
- Added management-friendly dataset preview and **Yang perlu diketahui sebelum analisis** section.
- Added direct navigation actions to Neural Graph, Fragmentation Analysis, and AI Analyst when the dataset is ready.
- Moved import history and destructive reset controls into a secondary dataset-management expander.
- Added `src/quality/readiness.py` and regression tests for readiness behavior.

## Load Data UI Refinement

- Mengurangi whitespace di bagian atas halaman agar area kerja lebih cepat terlihat.
- Menghapus numbering step yang membingungkan dan menggantinya dengan section label yang konsisten.
- Memperkuat upload area dengan visual hierarchy, upload icon, dan status dataset aktif yang mengikuti readiness aktual.
- Mengganti KPI Streamlit standar dengan card KPI custom yang lebih ringkas, memiliki visual distinction, tooltip, dan periode data dua baris agar tidak terpotong.
- Menghilangkan duplikasi badge status pada Data Readiness; status utama dipusatkan pada dataset aktif.
- Memadatkan Data Readiness dan Preview Dataset agar CTA analisis lebih dekat ke viewport pertama.
- Preview dibatasi 8 baris, nama kolom dibuat lebih terkontrol, serta nilai teks kosong tidak lagi tampil sebagai `nan`.
- Memperkuat panel "Yang perlu diketahui sebelum analisis" dan shortcut ke Neural Graph, Fragmentation, dan AI Analyst.

## Neural Graph legend refinement
- Moved the node metric color scale from the right side to a horizontal legend below the graph so it is not mistaken for a Y axis.
- Renamed the legend title to `Warna node — <metric>`.
- Added explicit guidance that spring-layout node position represents network structure only, not total hours or another node metric.
- Clarified that the selected node metric is read from hover values plus node size/color.
- Increased bottom chart margin so the horizontal color legend remains readable.
