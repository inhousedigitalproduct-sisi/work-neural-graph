from __future__ import annotations

import os
from configparser import ConfigParser
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppConfig:
    db_path: Path
    log_level: str = "INFO"
    llm_config_path: Path = Path("config/llm.conf")
    llm_provider: str = "openai"
    llm_model: str = "gpt-5-mini"
    llm_api_key_env: str = "OPENAI_API_KEY"
    llm_timeout_seconds: int = 180
    llm_enabled: bool = True
    llm_role: str = "interpretation"
    ollama_host: str = "http://localhost:11434"
    embedding_enabled: bool = False
    embedding_provider: str = "ollama"
    embedding_model: str = "qwen3-embedding:0.6b"


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

    llm_provider = os.getenv(
        "LLM_PROVIDER",
        parser.get("llm", "provider", fallback="openai"),
    ).strip().lower()
    llm_model = os.getenv(
        "LLM_MODEL",
        parser.get("llm", "model", fallback="gpt-5-mini"),
    ).strip()
    llm_api_key_env = os.getenv(
        "LLM_API_KEY_ENV",
        parser.get("llm", "api_key_env", fallback="OPENAI_API_KEY"),
    ).strip()
    llm_timeout_seconds = int(
        os.getenv(
            "LLM_TIMEOUT_SECONDS",
            parser.get("llm", "timeout_seconds", fallback="180"),
        )
    )
    llm_enabled = parser.getboolean("analytics", "llm_enabled", fallback=True)
    llm_role = parser.get("analytics", "llm_role", fallback="interpretation").strip()

    ollama_host = os.getenv(
        "OLLAMA_HOST",
        parser.get("ollama", "host", fallback="http://localhost:11434"),
    ).rstrip("/")

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
        llm_provider=llm_provider,
        llm_model=llm_model,
        llm_api_key_env=llm_api_key_env,
        llm_timeout_seconds=llm_timeout_seconds,
        llm_enabled=llm_enabled,
        llm_role=llm_role,
        ollama_host=ollama_host,
        embedding_enabled=embedding_enabled,
        embedding_provider=embedding_provider,
        embedding_model=embedding_model,
    )
