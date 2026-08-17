# LLM and Semantic Architecture

## Purpose

LLM layer menyediakan provider abstraction untuk interpretation/generation dan konfigurasi OpenAI/Ollama. Semantic embedding harus tetap optional terhadap deterministic analytics.

## Business Flow

```text
AppConfig / llm.conf + environment secrets
 -> provider profile
 -> dispatcher/service
 -> provider client
 -> generation/health result
```

Embedding/topic logic yang digunakan Quality Audit tidak boleh membuat deterministic audit bergantung pada provider availability.

## Entry Points and Dependencies

- `src/llm/client.py`: provider communication/error handling.
- `dispatcher.py`: routing/provider dispatch.
- `models.py`: LLM models/contracts.
- `prompts.py`: prompt definitions.
- `service.py`: higher-level LLM operations.
- `src/utils/config.py` + `config/llm.conf`: configuration.

## Current Risks and Non-standard Code

- Configuration masih membawa backward-compatible aliases/legacy environment behavior; berguna untuk migration tetapi menambah complexity.
- Provider health tidak sama dengan generation quota/readiness; UI harus mempertahankan distinction ini.
- Semantic helpers untuk Quality Audit sebagian berada di quality module, sehingga boundary semantic/LLM belum sepenuhnya jelas.

## Refactor Recommendations

1. Pertahankan typed provider result/error contract.
2. Isolasi embedding adapter dari deterministic quality package.
3. Dokumentasikan dan akhirnya sunset legacy config aliases setelah migration window.
4. Jangan membaca API key value dari file config atau menuliskannya ke log/test fixture.

## Tests

Current coverage utama: `tests/test_llm.py`, `test_llm_config.py`, dan `test_openai_errors.py`.

## Change Contract

Perubahan provider, model/config precedence, timeout, health semantics, error mapping, prompt contract, atau embedding execution harus meng-update dokumen ini dan provider/config regression tests.