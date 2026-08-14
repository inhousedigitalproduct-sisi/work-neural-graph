from __future__ import annotations

import os
from configparser import ConfigParser
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class LLMProfile:
    provider: str
    model: str
    api_key_env: str = ""
    host: str = ""


@dataclass(frozen=True)
class AppConfig:
    db_path: Path
    log_level: str = "INFO"
    llm_config_path: Path = Path("config/llm.conf")
    llm_default_provider: str = "openai"
    llm_timeout_seconds: int = 180
    llm_enabled: bool = True
    llm_role: str = "interpretation"
    openai_model: str = "gpt-5-mini"
    openai_api_key_env: str = "OPENAI_API_KEY"
    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "qwen3.5:4b"
    embedding_enabled: bool = False
    embedding_provider: str = "ollama"
    embedding_model: str = "qwen3-embedding:0.6b"

    @property
    def llm_provider(self) -> str:
        """Backward-compatible alias for the configured default provider."""
        return self.llm_default_provider

    @property
    def llm_model(self) -> str:
        """Backward-compatible model for the configured default provider."""
        return self.llm_profile(self.llm_default_provider).model

    @property
    def llm_api_key_env(self) -> str:
        """Backward-compatible API-key environment variable name."""
        return self.openai_api_key_env

    def llm_profile(self, provider: str) -> LLMProfile:
        provider_name = provider.strip().lower()
        if provider_name == "openai":
            return LLMProfile(
                provider="openai",
                model=self.openai_model,
                api_key_env=self.openai_api_key_env,
            )
        if provider_name == "ollama":
            return LLMProfile(
                provider="ollama",
                model=self.ollama_model,
                host=self.ollama_host,
            )
        raise ValueError(f"Unsupported LLM provider: {provider}")


def _load_parser(config_path: Path) -> ConfigParser:
    parser = ConfigParser()
    if config_path.exists():
        parser.read(config_path, encoding="utf-8")
    return parser


def get_config() -> AppConfig:
    db_path = Path(os.getenv("WNG_DB_PATH", "data/work_neural_graph.db"))
    log_level = os.getenv("WNG_LOG_LEVEL", "INFO").upper()
    llm_config_path = Path(os.getenv("WNG_LLM_CONFIG", "config/llm.conf"))
    parser = _load_parser(llm_config_path)

    # Backward compatibility: older llm.conf files stored provider/model directly
    # in [llm]. Newer files use [llm] only for defaults and provider profiles
    # in [openai] and [ollama].
    legacy_provider = parser.get("llm", "provider", fallback="openai").strip().lower()
    llm_default_provider = os.getenv(
        "LLM_PROVIDER",
        parser.get("llm", "default_provider", fallback=legacy_provider),
    ).strip().lower()
    llm_timeout_seconds = int(
        os.getenv(
            "LLM_TIMEOUT_SECONDS",
            parser.get("llm", "timeout_seconds", fallback="180"),
        )
    )
    llm_enabled = parser.getboolean("analytics", "llm_enabled", fallback=True)
    llm_role = parser.get("analytics", "llm_role", fallback="interpretation").strip()

    legacy_model = parser.get("llm", "model", fallback="").strip()
    legacy_api_key_env = parser.get("llm", "api_key_env", fallback="OPENAI_API_KEY").strip()

    openai_model = os.getenv(
        "OPENAI_MODEL",
        parser.get(
            "openai",
            "model",
            fallback=legacy_model if legacy_provider == "openai" and legacy_model else "gpt-5-mini",
        ),
    ).strip()
    openai_api_key_env = os.getenv(
        "LLM_API_KEY_ENV",
        parser.get("openai", "api_key_env", fallback=legacy_api_key_env or "OPENAI_API_KEY"),
    ).strip()

    ollama_host = os.getenv(
        "OLLAMA_HOST",
        parser.get("ollama", "host", fallback="http://localhost:11434"),
    ).rstrip("/")
    ollama_model = os.getenv(
        "OLLAMA_MODEL",
        parser.get(
            "ollama",
            "model",
            fallback=legacy_model if legacy_provider == "ollama" and legacy_model else "qwen3.5:4b",
        ),
    ).strip()

    # Preserve the old LLM_MODEL override by applying it to the configured
    # default provider only.
    legacy_model_override = os.getenv("LLM_MODEL", "").strip()
    if legacy_model_override:
        if llm_default_provider == "ollama":
            ollama_model = legacy_model_override
        else:
            openai_model = legacy_model_override

    embedding_enabled = parser.getboolean("embedding", "enabled", fallback=False)
    embedding_provider = parser.get("embedding", "provider", fallback="ollama").strip().lower()
    embedding_model = os.getenv(
        "OLLAMA_EMBEDDING_MODEL",
        parser.get("embedding", "model", fallback="qwen3-embedding:0.6b"),
    ).strip()

    return AppConfig(
        db_path=db_path,
        log_level=log_level,
        llm_config_path=llm_config_path,
        llm_default_provider=llm_default_provider,
        llm_timeout_seconds=llm_timeout_seconds,
        llm_enabled=llm_enabled,
        llm_role=llm_role,
        openai_model=openai_model,
        openai_api_key_env=openai_api_key_env,
        ollama_host=ollama_host,
        ollama_model=ollama_model,
        embedding_enabled=embedding_enabled,
        embedding_provider=embedding_provider,
        embedding_model=embedding_model,
    )
