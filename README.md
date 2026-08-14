# Work Neural Graph

Work Neural Graph is a local-first Streamlit application for importing timesheet files, normalizing them into a deterministic internal schema, persisting the result to SQLite, exploring cross-date task continuity as an interactive graph, analyzing fragmentation/continuity/context switching/concurrency with deterministic Python metrics, and optionally using a configured LLM provider as an interpretation layer.

## Phase 04 Scope

This phase includes everything from Phases 01-03 plus:

- Streamlit application bootstrap
- CSV and XLSX ingestion
- Source column mapping with auto-suggestions and override support
- Validation and normalization into a canonical schema
- Deterministic `task_key` and `entry_id` generation
- SQLite persistence with duplicate import prevention
- Date-to-date graph engine using NetworkX
- Interactive Plotly neural graph page
- Shared graph filters for date range, employee, project, and task
- Sequential and all-to-all relationship strategies
- Node and edge summary metadata for graph exploration
- Fragmentation analytics per task
- Continuity analytics per task
- Context switching analytics per employee and date
- Concurrency analytics for employee/date, project/date, and overall dates
- KPI service reused by the Dashboard, Neural Graph, and Fragmentation pages
- Dedicated Fragmentation analysis page with a task timeline
- Provider-based LLM configuration in `config/llm.conf`
- OpenAI API support for AI Analyst explanations
- Ollama client retained as an optional fallback provider
- Strict structured intent parsing and structured explanation schemas
- Safe deterministic analytics dispatcher
- Dedicated AI Analyst page
- Graceful degradation when the configured LLM provider is unavailable
- Synthetic sample dataset
- Unit tests for loading, normalization, validation, persistence, graph building, analytics, and LLM flows

This phase intentionally does not implement Phase 05 graph intelligence enhancements yet.

## Project Structure

```text
.
├── app.py
├── config/
│   └── llm.conf
├── data/
│   └── sample_timesheet.csv
├── pages/
│   └── 1_Dashboard.py
│   └── 2_Neural_Graph.py
│   └── 3_Fragmentation.py
│   └── 4_AI_Analyst.py
├── src/
│   ├── analytics/
│   ├── database/
│   ├── domain/
│   ├── graph/
│   ├── ingestion/
│   ├── llm/
│   ├── ui/
│   └── utils/
├── tests/
├── .env.example
└── requirements.txt
```

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

The default LLM provider is OpenAI. Keep the API key outside source code and outside Git:

```bash
export OPENAI_API_KEY="your_api_key_here"
```

For a persistent macOS shell configuration, place the export in `~/.zshrc` and reload the shell. Never commit an API key to this repository.

## LLM Configuration

Runtime LLM settings are stored in `config/llm.conf`:

```ini
[llm]
provider = openai
model = gpt-5-mini
api_key_env = OPENAI_API_KEY
timeout_seconds = 180

[embedding]
enabled = false
provider = ollama
model = qwen3-embedding:0.6b
```

`api_key_env` contains only the environment variable name. The secret value itself must remain in the local/server environment.

The default embedding model remains configured but disabled. It is reserved for future semantic task intelligence and is not required by the current AI Analyst flow.

To use Ollama instead of OpenAI, change the `[llm]` provider/model in `config/llm.conf` and ensure the configured Ollama model is installed locally.

## Run Tests

```bash
python -m pytest
```

## Run the App

```bash
streamlit run app.py
```

Open the dashboard and upload a `.csv` or `.xlsx` timesheet. The app previews the raw input, lets you confirm column mappings, validates rows, normalizes records, stores them in SQLite, and then displays the imported dataset.

Open the Neural Graph page to filter the imported data and render date-to-date task continuity.

Open the Fragmentation page to inspect deterministic KPI summaries, task fragmentation tables, context switching, and a simple task timeline.

Open the AI Analyst page to ask grounded questions. The LLM never reads the database directly; it only interprets deterministic Python results.

## Graph Concept

- Node meaning: one node represents one work date.
- Edge meaning: one edge represents one or more tasks that continue from one work date to another.
- Default strategy: `SEQUENTIAL`, which only links adjacent occurrence dates for the same `task_key`.
- Optional strategy: `ALL_TO_ALL`, which links every occurrence date pair for the same `task_key`.
- Node size: configurable, with `total_hours` as the default metric.
- Edge width: configurable, with `task_count` as the default metric.
- Hover behavior: nodes show date, hours, task count, employee count, and project count; edges show gap days, shared tasks, employees, projects, and related hours.

### Example

For a task that appears on `2026-08-01`, `2026-08-03`, and `2026-08-07`:

- `SEQUENTIAL` creates `2026-08-01 -> 2026-08-03` and `2026-08-03 -> 2026-08-07`
- `ALL_TO_ALL` also adds `2026-08-01 -> 2026-08-07`

Multiple rows for the same task on the same date are consolidated before relationships are created, so duplicate same-date entries do not create self-links.

## Analytics Definitions

### Fragmentation

Fragmentation is measured per `task_key` from its distinct work dates.

- `active_days`: number of distinct work dates
- `calendar_span_days`: inclusive span from first work date to last work date
- `continuation_count`: `max(active_days - 1, 0)`
- `date_gap_days`: day difference between adjacent work dates
- `interruption_days`: `max(date_gap_days - 1, 0)`
- `interruption_count`: number of adjacent date transitions where `date_gap_days > 1`
- `total_interruption_days`: sum of interruption days across transitions

Fragmentation score formula:

```text
fragmentation_score = continuation_count + total_interruption_days
```

Example for dates `2026-08-01`, `2026-08-03`, and `2026-08-07`:

- date gaps = `2`, `4`
- interruption days = `1`, `3`
- continuation count = `2`
- total interruption days = `4`
- fragmentation score = `6`

### Continuity

Continuity is measured with:

```text
continuous_work_ratio = active_days / calendar_span_days
```

The ratio is in the `0..1` range. Higher values mean work is spread across more of the days inside its own calendar span. It is not a productivity score.

### Context Switching

Context switching is measured per employee per work date.

- `unique_tasks`: number of distinct tasks worked on by the employee that day
- `context_switches`: `max(unique_tasks - 1, 0)`

If an employee touches 3 distinct tasks on one date, the context switch count for that day is `2`.

### Concurrency

Concurrency is reported as:

- employee/date: `parallel_tasks`
- project/date: `active_tasks`, `active_employees`
- date overall: `active_tasks`, `active_projects`, `active_employees`

## AI Analyst Architecture

Core principle:

```text
Python is the truth engine. The configured LLM is the interpretation engine.
```

The AI path is:

```text
User Question
  -> Structured Intent Parser
  -> Validated Intent
  -> Safe Python Dispatcher
  -> Deterministic Result Payload
  -> Structured LLM Explanation
```

The LLM does not generate SQL, does not generate Python, and does not become the source of truth.

### Default Provider

The default provider is OpenAI with `gpt-5-mini`. The application uses the API key referenced by `api_key_env` in `config/llm.conf`; by default this is `OPENAI_API_KEY`.

The application never stores or prints the API key. If the key is missing or the provider is unavailable, the deterministic analytics pages continue to work.

### Optional Ollama Fallback

Ollama support remains available as an alternative provider. The default local endpoint is:

```text
http://localhost:11434
```

When using Ollama, install the selected model locally and configure the `[llm]` section accordingly.

### Supported Intents

- `fragmentation`
- `continuity`
- `context_switch`
- `graph_summary`
- `project_comparison`
- `task_summary`

### Provider Failure Behavior

If the configured LLM provider or model is unavailable:

- Dashboard still works
- Neural Graph still works
- Fragmentation page still works
- AI Analyst keeps the deterministic summary and shows a clear provider status/error instead of crashing

## Environment

Use `.env.example` as a reference. Important variables include:

- `WNG_DB_PATH`: SQLite database location
- `WNG_LOG_LEVEL`: Python logging level
- `WNG_LLM_CONFIG`: path to the LLM configuration file, default `config/llm.conf`
- `OPENAI_API_KEY`: OpenAI API secret; set only in the local/server environment
- `LLM_PROVIDER`, `LLM_MODEL`, `LLM_TIMEOUT_SECONDS`: optional runtime overrides

## Definition of Done Notes

- Business logic is kept out of Streamlit page files.
- SQLite access is isolated in the repository layer.
- Duplicate imports are prevented by file SHA-256 hash.
- The graph engine is deterministic and built in Python.
- Same date-pair task continuations are aggregated into one final edge.
- Analytics are deterministic and derived from filtered data, not from LLM output.
- The AI Analyst uses validated structured intent plus deterministic payloads before any model explanation.
- API secrets are not stored in source code or tracked configuration files.
- Normalized schema fields are:
  - `entry_id`
  - `employee`
  - `work_date`
  - `project`
  - `task`
  - `task_key`
  - `hours`
  - `source_file`
  - `source_hash`

## Remaining TODOs

- Add graph intelligence enhancements in Phase 05.
- Add richer import history views and row-level validation summaries.
- Activate and implement embedding-based semantic task intelligence when required.

## Limitations

- Fragmentation scoring is intentionally simple and explainable; it is not a performance rating.
- Context switching is inferred from distinct tasks per day and does not model intra-day ordering.
- Timeline detail is task-level only in this phase.
- The AI Analyst is stateless per question in this phase.
- Explanations remain bounded by the deterministic payload and cannot infer root causes from timesheet data alone.
