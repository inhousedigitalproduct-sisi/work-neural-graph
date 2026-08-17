from __future__ import annotations

import argparse
import subprocess

from governance import ROOT, changed_files, impacted_modules, is_production_change, load_config


def main() -> int:
    parser = argparse.ArgumentParser(description="Run tests selected by changed production modules.")
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", required=True)
    args = parser.parse_args()

    config = load_config()
    files = changed_files(args.base, args.head)
    production_files = [path for path in files if is_production_change(path, config)]
    modules = impacted_modules(production_files, config)

    if not production_files:
        print("No production-code change detected; skipping application pytest selection.")
        return 0

    selected: set[str] = set()
    for module in modules.values():
        for pattern in module.get("tests") or []:
            selected.update(str(path.relative_to(ROOT)) for path in ROOT.glob(pattern) if path.is_file())

    if not selected:
        print("No mapped tests found for impacted modules.")
        return 2

    command = ["python", "-m", "pytest", "-q", *sorted(selected)]
    print("Running: " + " ".join(command))
    return subprocess.run(command, cwd=ROOT).returncode


if __name__ == "__main__":
    raise SystemExit(main())
