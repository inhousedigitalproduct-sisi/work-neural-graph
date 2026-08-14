from __future__ import annotations

from src.llm.client import OpenAIClient
from src.utils.config import get_config


def test_default_llm_config_uses_openai_without_storing_secret(monkeypatch) -> None:
    for name in (
        "WNG_LLM_CONFIG",
        "LLM_PROVIDER",
        "LLM_MODEL",
        "LLM_API_KEY_ENV",
        "LLM_TIMEOUT_SECONDS",
    ):
        monkeypatch.delenv(name, raising=False)

    config = get_config()

    assert config.llm_provider == "openai"
    assert config.llm_model == "gpt-5-mini"
    assert config.llm_api_key_env == "OPENAI_API_KEY"
    assert config.llm_timeout_seconds == 180
    assert config.embedding_enabled is False
    assert config.embedding_model == "qwen3-embedding:0.6b"


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
