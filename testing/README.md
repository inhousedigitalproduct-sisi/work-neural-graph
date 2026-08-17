# Testing and Architecture Governance

Folder `testing/` berisi **tooling**, bukan pengganti `tests/`.

```text
testing/
├── README.md
├── requirements.txt
├── architecture-impact.yml
└── scripts/
    ├── governance.py
    ├── screen_change.py
    ├── run_changed_tests.py
    └── validate_architecture_docs.py
```

- `tests/`: pytest unit/integration/regression test cases aplikasi.
- `testing/`: change screening, architecture impact mapping, selective runner, dan governance validation.

## Standard workflow

Sebelum production code di-commit ke `main`:

1. update module architecture doc yang terdampak;
2. add/update relevant pytest test;
3. validate docs;
4. screen architecture/test impact;
5. run selected tests.

```bash
python testing/scripts/validate_architecture_docs.py
python testing/scripts/screen_change.py --base <base-sha> --head <head-sha>
python testing/scripts/run_changed_tests.py --base <base-sha> --head <head-sha>
```

`architecture-impact.yml` adalah source of truth path -> module doc -> test selection. Bila struktur source berubah, mapping ini harus ikut diperbarui.