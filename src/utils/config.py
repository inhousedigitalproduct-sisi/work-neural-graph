from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppConfig:
    db_path: Path
    log_level: str = "INFO"
    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "qwen3.5:4b"
    ollama_embedding_model: str = "qwen3-embedding:0.6b"
    ollama_timeout_seconds: int = 180


def get_config() -> AppConfig:
    db_path = Path(os.getenv("WNG_DB_PATH", "data/work_neural_graph.db"))
    log_level = os.getenv("WNG_LOG_LEVEL", "INFO").upper()
    ollama_host = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
    ollama_model = os.getenv("OLLAMA_MODEL", "qwen3.5:4b")
    ollama_embedding_model = os.getenv("OLLAMA_EMBEDDING_MODEL", "qwen3-embedding:0.6b")
    ollama_timeout_seconds = int(os.getenv("OLLAMA_TIMEOUT_SECONDS", "180"))
    return AppConfig(
        db_path=db_path,
        log_level=log_level,
        ollama_host=ollama_host,
        ollama_model=ollama_model,
        ollama_embedding_model=ollama_embedding_model,
        ollama_timeout_seconds=ollama_timeout_seconds,
    )
