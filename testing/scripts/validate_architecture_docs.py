from __future__ import annotations

import sys
from pathlib import Path

from governance import ROOT, load_config

REQUIRED_ARCHITECTURE_HEADINGS = [
    "# Architecture",
    "## Target Layering",
    "## Dependency Rules",
    "## Change Governance",
    "## Testing Standard",
]

REQUIRED_MODULE_HEADINGS = [
    "## Purpose",
    "## Business Flow",
    "## Entry Points and Dependencies",
    "## Current Risks and Non-standard Code",
    "## Refactor Recommendations",
    "## Tests",
    "## Change Contract",
]


def missing_headings(path: Path, headings: list[str]) -> list[str]:
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    return [heading for heading in headings if heading not in text]


def main() -> int:
    config = load_config()
    errors: list[str] = []

    architecture = ROOT / "docs" / "architecture" / "Architecture.md"
    if not architecture.exists():
        errors.append("Missing docs/architecture/Architecture.md")
    else:
        for heading in missing_headings(architecture, REQUIRED_ARCHITECTURE_HEADINGS):
            errors.append(f"{architecture.relative_to(ROOT)} missing heading: {heading}")

    for name, module in (config.get("modules") or {}).items():
        doc_value = str(module.get("doc", "")).strip()
        if not doc_value:
            errors.append(f"Module '{name}' has no architecture doc mapping")
            continue
        path = ROOT / doc_value
        if not path.exists():
            errors.append(f"Missing architecture doc for '{name}': {doc_value}")
            continue
        for heading in missing_headings(path, REQUIRED_MODULE_HEADINGS):
            errors.append(f"{doc_value} missing heading: {heading}")

    if errors:
        print("Architecture documentation validation failed:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    print("Architecture documentation validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
