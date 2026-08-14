from __future__ import annotations

import json
import socket
from types import SimpleNamespace
from urllib import error

import pandas as pd
import pytest

from src.analytics.kpi import AnalyticsKPI
from src.analytics.service import AnalyticsSnapshot
from src.domain.models import GraphStrategy
from src.graph.builder import GraphBuildResult, GraphFilterConfig, GraphSummary
from src.llm.client import (
    OllamaClient,
    OllamaMalformedResponseError,
    OllamaTimeoutError,
    OllamaUnavailableError,
    StructuredChatResult,
)
from src.llm.dispatcher import execute_intent
from src.llm.models import AIExplanation, AnalysisFilters, AnalysisIntent, LLMMessage
from src.llm.service import AIAnalystService


class FakeHTTPResponse:
    def __init__(self, body: str) -> None:
        self.body = body.encode("utf-8")

    def read(self) -> bytes:
        return self.body

    def __enter__(self) -> "FakeHTTPResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


class FakeAnalyticsService:
    def __init__(self) -> None:
        self.last_filters = None

    def build_snapshot(self, filters: GraphFilterConfig, strategy: GraphStrategy = GraphStrategy.SEQUENTIAL) -> AnalyticsSnapshot:
        self.last_filters = filters
        filtered = pd.DataFrame(
            [
                {
                    "employee": "Ari",
                    "work_date": "2026-08-01",
                    "project": "FORCA ERP",
                    "task": "Fix Purchase Order",
                    "task_key": "forca erp::fix purchase order",
                    "hours": 3.0,
                }
            ]
        )
        fragmentation = pd.DataFrame(
            [
                {
                    "task_key": "forca erp::fix purchase order",
                    "task": "Fix Purchase Order",
                    "project": "FORCA ERP",
                    "employees": ["Ari"],
                    "total_hours": 3.0,
                    "active_days": 3,
                    "calendar_span_days": 7,
                    "fragmentation_score": 6,
                    "interruption_count": 2,
                    "continuous_work_ratio": 0.4286,
                }
            ]
        )
        continuity = pd.DataFrame(
            [
                {
                    "task_key": "forca erp::fix purchase order",
                    "task": "Fix Purchase Order",
                    "project": "FORCA ERP",
                    "active_days": 3,
                    "calendar_span_days": 7,
                    "continuous_work_ratio": 0.4286,
                }
            ]
        )
        context_daily = pd.DataFrame(
            [
                {
                    "employee": "Ari",
                    "work_date": pd.Timestamp("2026-08-01"),
                    "unique_tasks": 3,
                    "unique_projects": 2,
                    "context_switches": 2,
                }
            ]
        )
        context_summary = pd.DataFrame(
            [
                {
                    "employee": "Ari",
                    "average_context_switches_per_active_day": 2.0,
                    "max_context_switches_single_day": 2,
                }
            ]
        )
        graph_result = GraphBuildResult(
            filtered_dataframe=filtered,
            node_dataframe=pd.DataFrame(),
            relationship_dataframe=pd.DataFrame(),
            edge_dataframe=pd.DataFrame(),
            graph=SimpleNamespace(number_of_nodes=lambda: 1, number_of_edges=lambda: 0),
            summary=GraphSummary(
                nodes=1,
                edges=0,
                active_days=1,
                unique_tasks=1,
                total_hours=3.0,
                average_degree=0.0,
                connected_components=1,
                density=0.0,
            ),
        )
        return AnalyticsSnapshot(
            filtered_dataframe=filtered,
            fragmentation=fragmentation,
            continuity=continuity,
            context_switch_daily=context_daily,
            context_switch_summary=context_summary,
            concurrency={"date_overall": pd.DataFrame(), "employee_date": pd.DataFrame(), "project_date": pd.DataFrame()},
            graph_result=graph_result,
            kpi=AnalyticsKPI(
                total_hours=3.0,
                active_days=1,
                unique_tasks=1,
                unique_employees=1,
                unique_projects=1,
                graph_nodes=1,
                graph_edges=0,
                fragmented_tasks=1,
                interrupted_tasks=1,
                average_context_switches=2.0,
                average_continuity_ratio=0.4286,
            ),
        )


class FakeClient:
    def __init__(self, intent: AnalysisIntent | None = None, explanation: AIExplanation | None = None) -> None:
        self.model = "qwen3.5"
        self.intent = intent
        self.explanation = explanation

    def healthcheck(self):
        from src.llm.client import OllamaStatus

        return OllamaStatus(True, "http://localhost:11434", self.model, "Ollama is available.", (self.model,))

    def structured_chat(self, messages, response_model, temperature: float = 0.0):
        if response_model is AnalysisIntent:
            if self.intent is None:
                raise OllamaMalformedResponseError("invalid structured JSON")
            return StructuredChatResult(parsed=self.intent, raw_content=self.intent.model_dump_json(), duration_seconds=0.2)
        if self.explanation is None:
            raise OllamaMalformedResponseError("invalid structured JSON")
        return StructuredChatResult(
            parsed=self.explanation,
            raw_content=self.explanation.model_dump_json(),
            duration_seconds=0.3,
        )


def test_client_successful_structured_response(monkeypatch) -> None:
    def fake_urlopen(req, timeout):
        if req.full_url.endswith("/api/chat"):
            return FakeHTTPResponse(json.dumps({"message": {"content": '{"summary":"ok","observations":[],"risks_or_attention_points":[],"recommended_investigation":[]}'}}))
        return FakeHTTPResponse(json.dumps({"models": [{"name": "qwen3.5"}]}))

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    client = OllamaClient(host="http://localhost:11434", model="qwen3.5", timeout_seconds=5)
    result = client.structured_chat(
        messages=[LLMMessage(role="user", content="hello")],
        response_model=AIExplanation,
    )
    assert result.parsed.summary == "ok"


def test_client_timeout(monkeypatch) -> None:
    def fake_urlopen(req, timeout):
        raise error.URLError(socket.timeout("timed out"))

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    client = OllamaClient(host="http://localhost:11434", model="qwen3.5", timeout_seconds=1)
    with pytest.raises(OllamaTimeoutError):
        client.list_models()


def test_client_connection_failure(monkeypatch) -> None:
    def fake_urlopen(req, timeout):
        raise error.URLError(ConnectionRefusedError("refused"))

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    client = OllamaClient(host="http://localhost:11434", model="qwen3.5", timeout_seconds=1)
    with pytest.raises(OllamaUnavailableError):
        client.list_models()


def test_client_malformed_json(monkeypatch) -> None:
    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout: FakeHTTPResponse("not-json"))
    client = OllamaClient(host="http://localhost:11434", model="qwen3.5", timeout_seconds=1)
    with pytest.raises(OllamaMalformedResponseError):
        client.list_models()


def test_model_unavailable_behavior(monkeypatch) -> None:
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda req, timeout: FakeHTTPResponse(json.dumps({"models": [{"name": "llama3"}]})),
    )
    client = OllamaClient(host="http://localhost:11434", model="qwen3.5", timeout_seconds=1)
    status = client.healthcheck()
    assert not status.available
    assert "was not found" in status.message


def test_valid_fragmentation_intent() -> None:
    intent = AnalysisIntent.model_validate(
        {
            "analysis_type": "fragmentation",
            "metric": "fragmentation_score",
            "group_by": "task",
            "filters": {"projects": ["FORCA ERP"]},
            "sort": "desc",
            "limit": 5,
        }
    )
    assert intent.analysis_type == "fragmentation"
    assert intent.limit == 5


def test_unsupported_analysis_type_is_rejected() -> None:
    with pytest.raises(Exception):
        AnalysisIntent.model_validate(
            {
                "analysis_type": "shell_exec",
                "filters": {},
            }
        )


def test_invalid_date_range_is_rejected() -> None:
    with pytest.raises(Exception):
        AnalysisFilters.model_validate({"start_date": "2026-08-10", "end_date": "2026-08-01"})


def test_excessive_limit_is_rejected() -> None:
    with pytest.raises(Exception):
        AnalysisIntent.model_validate({"analysis_type": "fragmentation", "filters": {}, "limit": 99})


def test_dispatcher_routes_to_fragmentation() -> None:
    analytics_service = FakeAnalyticsService()
    intent = AnalysisIntent.model_validate(
        {"analysis_type": "fragmentation", "filters": {"projects": ["FORCA ERP"]}, "limit": 5}
    )
    result = execute_intent(intent, analytics_service)
    assert result.payload["analysis_type"] == "fragmentation"
    assert result.payload["rows"][0]["task"] == "Fix Purchase Order"
    assert analytics_service.last_filters.projects == ("FORCA ERP",)


def test_dispatcher_rejects_invalid_intent() -> None:
    analytics_service = FakeAnalyticsService()
    invalid_intent = AnalysisIntent.model_construct(
        analysis_type="shell_exec",
        metric=None,
        group_by=None,
        filters=AnalysisFilters(),
        sort="desc",
        limit=10,
    )
    with pytest.raises(ValueError):
        execute_intent(invalid_intent, analytics_service)


def test_explanation_structured_response_validation() -> None:
    analytics_service = FakeAnalyticsService()
    intent = AnalysisIntent.model_validate({"analysis_type": "fragmentation", "filters": {}})
    explanation = AIExplanation(
        summary="Ringkasan",
        observations=["Observasi 1"],
        risks_or_attention_points=["Perlu perhatian"],
        recommended_investigation=["Periksa backlog"],
    )
    service = AIAnalystService(analytics_service=analytics_service, client=FakeClient(intent=intent, explanation=explanation))
    result = service.answer_question("Task mana yang paling fragmented?", {"filters": {}, "dataset": {}})
    assert result.explanation is not None
    assert result.explanation.summary == "Ringkasan"


def test_malformed_explanation_is_handled_gracefully() -> None:
    analytics_service = FakeAnalyticsService()
    intent = AnalysisIntent.model_validate({"analysis_type": "fragmentation", "filters": {}})
    service = AIAnalystService(analytics_service=analytics_service, client=FakeClient(intent=intent, explanation=None))
    with pytest.raises(OllamaMalformedResponseError):
        service.answer_question("Task mana yang paling fragmented?", {"filters": {}, "dataset": {}})


def test_offline_status_does_not_break_core_service() -> None:
    class OfflineClient(FakeClient):
        def healthcheck(self):
            from src.llm.client import OllamaStatus

            return OllamaStatus(False, "http://localhost:11434", "qwen3.5", "offline", ())

    service = AIAnalystService(analytics_service=FakeAnalyticsService(), client=OfflineClient())
    status = service.get_status()
    assert not status.available
    assert status.message == "offline"
