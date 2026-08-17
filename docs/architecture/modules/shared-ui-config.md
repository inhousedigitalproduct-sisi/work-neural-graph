# Shared UI and Configuration Architecture

## Purpose

Shared UI/config menyediakan composition dan reusable controls agar page tidak membuat filter/config semantics sendiri-sendiri tanpa alasan.

## Business Flow

```text
app/page
 -> get_config
 -> shared UI components / filters
 -> feature service
 -> presentation
```

## Entry Points and Dependencies

- `app.py`: Streamlit application entry/composition.
- `src/ui/components.py`: shared filters, validation/summary components, state helpers.
- `src/utils/config.py`: `AppConfig`, provider profiles, environment/config precedence.
- `config/llm.conf`: non-secret provider defaults.

## Current Risks and Non-standard Code

- `src/ui/components.py` dapat menjadi catch-all bila semua presentation helper ditambahkan ke satu file.
- Beberapa page masih memiliki local formatting/chart helpers yang berpotensi reusable tetapi belum diekstrak.
- Backward compatibility config properties memperluas public surface sementara.

## Refactor Recommendations

1. Split UI component modules berdasarkan concern bila file terus tumbuh (filters, metrics, validation, formatters).
2. Jaga filter semantics di satu contract dan beri parameter eksplisit untuk variasi page.
3. Semua environment/config access melalui `get_config()`; jangan baca env langsung dari page.
4. Pindahkan reusable presentation helper hanya setelah ada reuse nyata, bukan abstraksi prematur.

## Tests

Config memiliki coverage di `tests/test_llm_config.py`. Shared UI saat ini lebih banyak diuji melalui feature behavior; tambahkan unit/contract tests jika shared filter logic bertambah kompleks.

## Change Contract

Perubahan global filter semantics, session-state cleanup, configuration precedence, provider profile, atau shared component contract wajib meng-update dokumen ini dan test config/feature consumer yang relevan.