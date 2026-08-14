from __future__ import annotations

import pandas as pd
import streamlit as st

from src.domain.models import DatasetSummary
from src.domain.models import GraphStrategy
from src.graph.builder import GraphFilterConfig
from src.utils.config import AppConfig


DATASET_STATE_PREFIXES = (
    "filter_",
    "mapping_",
    "load_data_",
    "neural_graph_",
    "fragmentation_",
    "ai_analyst_",
    "quality_audit_",
)

LLM_PROVIDER_STATE_KEY = "llm_runtime_provider"
LLM_PROVIDER_OPTIONS = ("openai", "ollama", "off")


def clear_dataset_dependent_state() -> None:
    keys_to_clear = [
        key
        for key in list(st.session_state.keys())
        if key.startswith(DATASET_STATE_PREFIXES)
    ]
    for key in keys_to_clear:
        del st.session_state[key]


def render_dataset_summary(summary: DatasetSummary) -> None:
    col1, col2, col3 = st.columns(3)
    col1.metric("Rows", f"{summary.row_count}")
    col2.metric("Employees", f"{summary.employee_count}")
    col3.metric("Projects", f"{summary.project_count}")

    col4, col5, col6 = st.columns(3)
    col4.metric("Tasks", f"{summary.task_count}")
    col5.metric("States", f"{summary.state_count}")
    col6.metric("Total Hours", f"{summary.total_hours:.2f}")

    col7, col8 = st.columns(2)
    col7.metric("Start Date", summary.start_date.isoformat() if summary.start_date else "-")
    col8.metric("End Date", summary.end_date.isoformat() if summary.end_date else "-")


def render_validation_result(errors: list[str], warnings: list[str]) -> None:
    if errors:
        for error in errors:
            st.error(error)
    if warnings:
        for warning in warnings:
            st.warning(warning)
    if not errors and not warnings:
        st.success("Validation passed with no warnings.")


def render_graph_summary(
    nodes: int,
    edges: int,
    active_days: int,
    unique_tasks: int,
    total_hours: float,
    average_degree: float,
) -> None:
    col1, col2, col3 = st.columns(3)
    col1.metric("Nodes", f"{nodes}")
    col2.metric("Edges", f"{edges}")
    col3.metric("Active Days", f"{active_days}")

    col4, col5, col6 = st.columns(3)
    col4.metric("Unique Tasks", f"{unique_tasks}")
    col5.metric("Total Hours", f"{total_hours:.2f}")
    col6.metric("Average Degree", f"{average_degree:.2f}")


def render_analytics_summary(
    total_hours: float,
    active_days: int,
    unique_tasks: int,
    unique_employees: int,
    unique_projects: int,
    fragmented_tasks: int,
    interrupted_tasks: int,
    average_context_switches: float,
    average_continuity_ratio: float,
) -> None:
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Hours", f"{total_hours:.2f}")
    col2.metric("Active Days", f"{active_days}")
    col3.metric("Tasks", f"{unique_tasks}")

    col4, col5, col6 = st.columns(3)
    col4.metric("Employees", f"{unique_employees}")
    col5.metric("Projects", f"{unique_projects}")
    col6.metric("Fragmented Tasks", f"{fragmented_tasks}")

    col7, col8, col9 = st.columns(3)
    col7.metric("Interrupted Tasks", f"{interrupted_tasks}")
    col8.metric("Avg Context Switches", f"{average_context_switches:.2f}")
    col9.metric("Avg Continuity", f"{average_continuity_ratio:.2f}")


def render_llm_provider_selector(config: AppConfig) -> str:
    """Render one global per-session LLM selector shared across AI-enabled pages."""
    default_provider = config.llm_default_provider if config.llm_enabled else "off"
    if default_provider not in LLM_PROVIDER_OPTIONS:
        default_provider = "openai"

    current_provider = st.session_state.get(LLM_PROVIDER_STATE_KEY)
    if current_provider not in LLM_PROVIDER_OPTIONS:
        st.session_state[LLM_PROVIDER_STATE_KEY] = default_provider

    with st.sidebar:
        st.divider()
        st.subheader("AI Interpretation")
        selected_provider = st.radio(
            "LLM",
            LLM_PROVIDER_OPTIONS,
            key=LLM_PROVIDER_STATE_KEY,
            horizontal=True,
            format_func=lambda value: {
                "openai": "OpenAI",
                "ollama": "Qwen Local",
                "off": "Off",
            }[value],
            help=(
                "Pilihan ini berlaku selama sesi Streamlit dan dipakai bersama oleh halaman AI Analyst dan Audit Kualitas. "
                "Mengubah pilihan tidak mengubah file config/llm.conf."
            ),
        )

        if selected_provider == "off":
            st.caption("Narasi AI nonaktif; analytics Python tetap berjalan.")
        else:
            profile = config.llm_profile(selected_provider)
            provider_label = "OpenAI" if selected_provider == "openai" else "Ollama"
            st.caption(f"{provider_label}: {profile.model}")

    return selected_provider


def render_shared_filters(
    dataframe: pd.DataFrame,
    include_strategy: bool = False,
) -> tuple[GraphFilterConfig, GraphStrategy | None]:
    source_dataframe = dataframe.copy()
    source_dataframe["work_date"] = pd.to_datetime(source_dataframe["work_date"])
    min_date = source_dataframe["work_date"].min().date()
    max_date = source_dataframe["work_date"].max().date()

    with st.sidebar:
        st.header("Dataset Filters")
        date_range = st.date_input("Date Range", value=(min_date, max_date), min_value=min_date, max_value=max_date)
        available_employees = sorted(source_dataframe["employee"].dropna().unique().tolist())
        employee_key = "filter_employee_names"
        st.session_state[employee_key] = [
            value for value in st.session_state.get(employee_key, []) if value in available_employees
        ]
        selected_employees = st.multiselect("Employees", available_employees, key=employee_key)

        available_projects = sorted(source_dataframe["project"].dropna().unique().tolist())
        project_key = "filter_projects"
        st.session_state[project_key] = [
            value for value in st.session_state.get(project_key, []) if value in available_projects
        ]
        selected_projects = st.multiselect("Projects", available_projects, key=project_key)
        task_options = source_dataframe.sort_values("task")["task_key"].unique().tolist()
        task_key = "filter_task_keys"
        st.session_state[task_key] = [
            value for value in st.session_state.get(task_key, []) if value in task_options
        ]
        selected_task_keys = st.multiselect(
            "Tasks",
            task_options,
            key=task_key,
            format_func=lambda value: value.split("::", 1)[1],
        )
        selected_states: list[str] = []
        if "state" in source_dataframe.columns:
            available_states = sorted(source_dataframe["state"].dropna().astype(str).unique().tolist())
            state_key = "filter_states"
            st.session_state[state_key] = [
                value for value in st.session_state.get(state_key, []) if value in available_states
            ]
            selected_states = st.multiselect("State", available_states, key=state_key)
        note_keyword = ""
        if "note" in source_dataframe.columns:
            note_keyword = st.text_input("Note keyword", key="filter_note_keyword")
        strategy = None
        if include_strategy:
            strategy = st.selectbox("Graph Strategy", list(GraphStrategy), format_func=lambda value: value.value)

    start_date = min_date
    end_date = max_date
    if isinstance(date_range, tuple):
        if len(date_range) >= 1 and date_range[0] is not None:
            start_date = date_range[0]
        if len(date_range) >= 2 and date_range[1] is not None:
            end_date = date_range[1]
    elif date_range is not None:
        start_date = end_date = date_range

    filters = GraphFilterConfig(
        employee_names=tuple(selected_employees),
        projects=tuple(selected_projects),
        task_keys=tuple(selected_task_keys),
        states=tuple(selected_states),
        note_keyword=note_keyword or None,
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
    )
    return filters, strategy
