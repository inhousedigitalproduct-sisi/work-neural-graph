# Architecture Documentation

Folder ini adalah living architecture documentation untuk Work Neural Graph.

Tujuannya bukan membekukan seluruh kondisi legacy sebagai standar, tetapi memisahkan dengan jelas:

- **current state**: bagaimana fitur bekerja hari ini, termasuk technical debt;
- **target architecture**: aturan yang harus diikuti untuk pengembangan berikutnya;
- **change governance**: dokumen dan test yang wajib ikut berubah ketika production code berubah.

## Tree

```text
docs/architecture/
├── README.md
├── Architecture.md
├── CHANGE_POLICY.md
├── decisions/
│   └── README.md
└── modules/
    ├── load-data.md
    ├── neural-graph.md
    ├── fragmentation.md
    ├── quality-audit.md
    ├── analytics.md
    ├── ingestion.md
    ├── persistence-services.md
    ├── llm-semantic.md
    └── shared-ui-config.md
```

## How to read

1. Mulai dari `Architecture.md` untuk standar target.
2. Baca `modules/<name>.md` untuk alur bisnis, dependency, risiko, dan rekomendasi refactor fitur tertentu.
3. Gunakan `CHANGE_POLICY.md` sebelum commit ke `main`.
4. Keputusan besar yang mengubah standar lintas modul harus dicatat sebagai ADR baru di `decisions/`.

## Baseline

Pemetaan awal dibuat terhadap `main` pada baseline commit `1bff3d2d4b07e36f422111b6294bb7a154e900d6`.

Dokumentasi modul wajib diperbarui bersamaan dengan perubahan production code yang dipetakan ke modul tersebut.