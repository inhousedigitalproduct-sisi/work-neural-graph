from __future__ import annotations

import json
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


SUPPORTED_ANALYSIS_TYPES = (
    "fragmentation",
    "continuity",
    "context_switch",
    "graph_summary",
    "project_comparison",
    "task_summary",
)


class AnalysisFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start_date: date | None = None
    end_date: date | None = None
    employees: list[str] | None = None
    projects: list[str] | None = None
    tasks: list[str] | None = None

    @model_validator(mode="after")
    def validate_date_order(self) -> "AnalysisFilters":
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError("start_date must be on or before end_date")
        return self

    @field_validator("employees", "projects", "tasks")
    @classmethod
    def limit_list_sizes(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        if len(value) > 20:
            raise ValueError("filter lists may contain at most 20 values")
        return value


class AnalysisIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    analysis_type: Literal[
        "fragmentation",
        "continuity",
        "context_switch",
        "graph_summary",
        "project_comparison",
        "task_summary",
    ]
    metric: Literal[
        "fragmentation_score",
        "continuous_work_ratio",
        "context_switches",
        "total_hours",
        "task_count",
        "graph_density",
    ] | None = None
    group_by: Literal["task", "employee", "project", "date"] | None = None
    filters: AnalysisFilters = Field(default_factory=AnalysisFilters)
    sort: Literal["asc", "desc"] = "desc"
    limit: int = Field(default=10, ge=1, le=20)


class AIExplanation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str
    observations: list[str]
    risks_or_attention_points: list[str]
    recommended_investigation: list[str]


class LLMMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class AnalystResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: AnalysisIntent
    result_payload: dict
    explanation: AIExplanation | None = None
    model: str | None = None
    duration_seconds: float | None = None


def format_json_schema(model_type: type[BaseModel]) -> str:
    return json.dumps(model_type.model_json_schema(), indent=2, sort_keys=True)
