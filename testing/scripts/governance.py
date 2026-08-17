from __future__ import annotations

import fnmatch
import subprocess
from pathlib import Path
from typing import Iterable

import yaml

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "testing" / "architecture-impact.yml"


def load_config() -> dict:
    with CONFIG_PATH.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def changed_files(base: str, head: str) -> list[str]:
    command = ["git", "diff", "--name-only", base, head, "--"]
    result = subprocess.run(command, cwd=ROOT, check=True, text=True, capture_output=True)
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def matches(path: str, patterns: Iterable[str]) -> bool:
    return any(fnmatch.fnmatch(path, pattern) for pattern in patterns)


def impacted_modules(files: Iterable[str], config: dict) -> dict[str, dict]:
    impacted: dict[str, dict] = {}
    for name, module in (config.get("modules") or {}).items():
        patterns = module.get("code") or []
        if any(matches(path, patterns) for path in files):
            impacted[name] = module
    return impacted


def is_production_change(path: str, config: dict) -> bool:
    production = config.get("production") or {}
    include = production.get("include") or []
    exclude = production.get("exclude") or []
    return matches(path, include) and not matches(path, exclude)
