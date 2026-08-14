from __future__ import annotations

import pytest

from src.llm.client import OpenAIClient
from src.utils.config import get_config


def _clear_llm_env(monkeypatch) -> None:
    for name in (
        "WNG_LLM_CONFIG",
        "LLM_PROVIDER",
        "LLM_MODEL",
        "LLM_API_KEY_ENV",
        "LLM_TIMEOUT_SECONDS",
        "OPENAI_MODEL",
        "OLLAMA_MODEL",
        "OLLAMA_HOST",
        "OLLAMA_EMBEDDING_MODEL",
    ):
        monkeypatch.delenv(name, raising=False)


def test_default_llm_config_uses_openai_without_storing_secret(monkeypatch) -> None:
    _clear_llm_env(monkeypatch)

    config = get_config()

    assert config.llm_default_provider == "openai"
    assert config.llm_provider == "openai"
    assert config.llm_model == "gpt-5-mini"
    assert config.llm_api_key_env == "OPENAI_API_KEY"
    assert config.llm_timeout_seconds == 180
    assert config.embedding_enabled is False
    assert config.embedding_model == "qwen3-embedding:0.6b"


def test_llm_config_registers_openai_and_ollama_profiles(monkeypatch) -> None:
    _clear_llm_env(monkeypatch)

    config = get_config()
    openai_profile = config.llm_profile("openai")
    ollama_profile = config.llm_profile("ollama")

    assert openai_profile.provider == "openai"
    assert openai_profile.model == "gpt-5-mini"
    assert openai_profile.api_key_env == "OPENAI_API_KEY"
    assert openai_profile.host == ""

    assert ollama_profile.provider == "ollama"
    assert ollama_profile.model == "qwen3.5:4b"
    assert ollama_profile.api_key_env == ""
    assert ollama_profile.host == "http://localhost:11434"


def test_llm_profile_rejects_unknown_provider(monkeypatch) -> None:
    _clear_llm_env(monkeypatch)
    config = get_config()

    with pytest.raises(ValueError, match="Unsupported LLM provider"):
        config.llm_profile("unknown")


def test_openai_client_reports_missing_environment_secret() -> None:
    client = OpenAIClient(
        api_key=None,
        model="gpt-5-mini",
        api_key_env="OPENAI_API_KEY",
    )

    status = client.healthcheck()

    assert status.available is False
    assert status.provider == "openai"
    assert status.model == "gpt-5-mini"
    assert "OPENAI_API_KEY" in status.message
