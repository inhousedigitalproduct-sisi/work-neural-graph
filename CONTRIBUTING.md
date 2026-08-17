# Development and Commit Convention

This repository uses descriptive commit messages to preserve context across incremental fixes, refactors, and feature development.

The goal is that someone reading Git history can understand **why a change was made, what changed, how it was validated, and what remains** without needing the original chat or developer session.

## Commit Message Format

Use the following structure for non-trivial changes:

```text
type(scope): short summary

Context:
- Why this change is needed.

Changes:
- What behavior, file, module, or configuration changed.
- Include important compatibility or migration details.

Validation:
- Tests or checks that were run.
- Include result when known, for example: python -m pytest -> 79 passed.
- If validation was not run, state that explicitly.

Follow-up:
- Remaining work, known limitations, or next action.
- Use "None" when there is no follow-up.
```

For a very small documentation-only or typo change, the short summary may be sufficient when the impact is obvious. For bug fixes, refactors, configuration changes, dependency changes, and feature work, use the full format above.

## Commit Types

- `feat`: new application capability or user-facing feature.
- `fix`: bug fix or compatibility correction.
- `refactor`: structural change without intentional behavior change.
- `test`: test additions or test-only changes.
- `docs`: documentation or developer guidance.
- `chore`: maintenance, dependency, tooling, or repository housekeeping.

Scopes should identify the affected area when useful, for example `quality-audit`, `llm`, `config`, `graph`, `ingestion`, or `repo`.

## Example: Bug Fix

```text
fix(quality-audit): align page with provider-based LLM config

Context:
- Quality Audit still referenced legacy AppConfig attributes after the multi-provider LLM refactor.

Changes:
- Replace legacy config access with provider profiles.
- Keep deterministic audit available when provider generation fails.

Validation:
- python -m pytest -> all selected tests passed.

Follow-up:
- None.
```

## Rules for Incremental Fixes

1. Do not use vague commit messages such as `update`, `fix`, `changes`, or `minor fix`.
2. An additional fix after a previous change should explain its relationship to the earlier work in the `Context` section.
3. Do not hide unrelated changes in the same commit. Keep the scope understandable.
4. Configuration migrations must mention old and new configuration names when relevant.
5. Dependency changes must mention why the dependency changed.
6. Security-sensitive changes must never include secret values in the commit message, source code, configuration, test output, or documentation.
7. If a change has not been validated locally, write `Validation: Not run` rather than implying that it passed.

## Architecture and Test Gate

Every production-code change targeting `main` must follow `docs/architecture/CHANGE_POLICY.md`.

Required outcomes before commit/push:

1. Screen changed code against `testing/architecture-impact.yml`.
2. Update the architecture module documentation for every impacted module.
3. Add or update a relevant pytest test under `tests/`.
4. Run `testing/scripts/validate_architecture_docs.py`.
5. Run the architecture/test impact screen.
6. Run the impacted-test selector.

Example after creating a local candidate commit:

```bash
BASE=$(git rev-parse HEAD^)
HEAD=$(git rev-parse HEAD)
python testing/scripts/validate_architecture_docs.py
python testing/scripts/screen_change.py --base "$BASE" --head "$HEAD"
python testing/scripts/run_changed_tests.py --base "$BASE" --head "$HEAD"
```

`tests/` remains the canonical pytest test suite. `testing/` contains governance and test-selection scripts, not a second test framework.

A GitHub Action repeats this gate on pushes to `main`. Because this repository may use direct-to-main commits, local/agent screening before commit is mandatory; the post-push Action is a safety net, not a substitute.

## Repository Change Report

After making a repository change, report at least:

```text
Commit: <sha>
Type: fix / feat / refactor / test / docs / chore
Changed:
- <file or module>: <what changed>
Validation:
- <command and result, or Not run>
Follow-up:
- <remaining item or None>
```

This reporting format should also be used when changes are made through ChatGPT so development context remains continuous between conversations.
