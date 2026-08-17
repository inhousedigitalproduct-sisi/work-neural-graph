# Architecture Change Policy

Policy ini berlaku untuk setiap perubahan yang akan masuk ke `main`.

## Definition of Done

Production change dianggap selesai hanya jika:

- changed files sudah di-screen terhadap `testing/architecture-impact.yml`;
- architecture document modul terdampak ikut di-update;
- test baru atau test existing yang relevan di-update di `tests/`;
- architecture docs validator pass;
- impacted tests pass;
- commit message menjelaskan context, changes, validation, dan follow-up.

## Required Commands

```bash
BASE=$(git rev-parse HEAD^)
HEAD=$(git rev-parse HEAD)
python testing/scripts/validate_architecture_docs.py
python testing/scripts/screen_change.py --base "$BASE" --head "$HEAD"
python testing/scripts/run_changed_tests.py --base "$BASE" --head "$HEAD"
```

Untuk perubahan yang belum di-commit, gunakan temporary local commit atau bandingkan terhadap `main` pada commit candidate. Jangan mengandalkan post-push CI sebagai satu-satunya screening.

## Architecture Update Rule

Setiap module doc memiliki section `Change Contract`. Update minimal harus menjawab:

- behavior/data flow apa yang berubah;
- dependency baru/dihapus;
- risiko/performance/security impact;
- test mana yang meng-cover perubahan;
- apakah rekomendasi refactor berubah.

Perubahan presentation copy yang benar-benar tidak mengubah architecture tetap harus melewati screening; jika path dipetakan sebagai production module, module doc dapat diberi entry change history singkat.

## Test Rule

Production code change wajib menyertakan add/update test Python di `tests/`. Tidak cukup hanya menjalankan test existing tanpa mencatat regression/behavior yang berubah.

Folder `testing/` adalah tooling governance dan selective runner. Actual application test cases tetap di `tests/` agar konsisten dengan pytest yang sudah ada.

## Direct-to-main Note

Push langsung ke `main` tidak dapat dicegah oleh workflow yang baru berjalan setelah push. Karena itu standar operasional adalah **screen + docs + tests sebelum commit/push**. GitHub Action `architecture-governance.yml` berfungsi sebagai safety net dan membuat pelanggaran terlihat segera.