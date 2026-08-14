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

Scopes should identify the affected area when useful, for example `ai-analyst`, `quality-audit`, `llm`, `config`, `graph`, `ingestion`, or `repo`.

## Example: Bug Fix

```text
fix(quality-audit): align page with provider-based LLM config

Context:
- Quality Audit still referenced legacy AppConfig attributes after the multi-provider LLM refactor.

Changes:
- Replace ollama_model with llm_model.
- Replace ollama_timeout_seconds with llm_timeout_seconds.
- Use embedding_model for semantic analysis.
- Build the AI service from llm_provider so OpenAI and Ollama use the same page flow.

Validation:
- python -m pytest -> 79 passed.

Follow-up:
- None.
```

## Example: Feature

```text
feat(llm): add provider-based LLM configuration

Context:
- AI Analyst needs to switch between OpenAI and local Ollama without source-code changes.

Changes:
- Add config/llm.conf.
- Add OpenAI client support.
- Keep Ollama as an optional local provider.
- Read API secrets only from environment variables.

Validation:
- python -m pytest -> all tests passed.

Follow-up:
- Embedding remains disabled until semantic intelligence is activated.
```

## Rules for Incremental Fixes

1. Do not use vague commit messages such as `update`, `fix`, `changes`, or `minor fix`.
2. An additional fix after a previous change should explain its relationship to the earlier work in the `Context` section.
3. Do not hide unrelated changes in the same commit. Keep the scope understandable.
4. Configuration migrations must mention old and new configuration names when relevant.
5. Dependency changes must mention why the dependency changed.
6. Security-sensitive changes must never include secret values in the commit message, source code, configuration, test output, or documentation.
7. If a change has not been validated locally, write `Validation: Not run` rather than implying that it passed.

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
