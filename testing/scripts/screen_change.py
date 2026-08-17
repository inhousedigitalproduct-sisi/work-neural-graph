from __future__ import annotations

import argparse
import sys

from governance import changed_files, impacted_modules, is_production_change, load_config, matches


def main() -> int:
    parser = argparse.ArgumentParser(description="Screen architecture and test impact for a Git change.")
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", required=True)
    args = parser.parse_args()

    config = load_config()
    files = changed_files(args.base, args.head)
    production_files = [path for path in files if is_production_change(path, config)]
    modules = impacted_modules(production_files, config)

    print("Changed files:")
    for path in files:
        print(f"  - {path}")

    if not production_files:
        print("No production-code change detected; architecture/test-change gate is not required.")
        return 0

    errors: list[str] = []
    for name, module in modules.items():
        doc = str(module.get("doc", "")).strip()
        if doc and doc not in files:
            errors.append(f"Architecture doc not updated for module '{name}': {doc}")

    if not modules:
        errors.append("Production code changed but no architecture module mapping matched it.")

    test_files = [path for path in files if path.startswith("tests/") and path.endswith(".py")]
    if not test_files:
        errors.append("Production code changed without adding/updating a Python test under tests/.")
    else:
        expected_patterns: list[str] = []
        for module in modules.values():
            expected_patterns.extend(module.get("tests") or [])
        if expected_patterns and not any(matches(path, expected_patterns) for path in test_files):
            errors.append(
                "Changed tests do not match the impacted-module test mapping. "
                "Update a relevant test or architecture-impact.yml."
            )

    if errors:
        print("\nGovernance screening failed:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    print("\nGovernance screening passed.")
    print("Impacted modules: " + ", ".join(sorted(modules)))
    print("Changed tests: " + ", ".join(test_files))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
