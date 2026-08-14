from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from src.analytics.service import AnalyticsService
from src.llm.client import (
    OllamaClient,
    OllamaError,
    OllamaMalformedResponseError,
    OllamaStatus,
)
from src.llm.dispatcher import execute_intent
from src.llm.models import AIExplanation, AnalysisIntent, AnalystResult, LLMMessage
from src.llm.prompts import EXPLANATION_SYSTEM_PROMPT, EXPLANATION_PROMPT_VERSION, INTENT_PROMPT_VERSION, INTENT_SYSTEM_PROMPT


@dataclass(frozen=True)
class ParsedIntentResult:
    intent: AnalysisIntent
    duration_seconds: float
    raw_content: str


class AIAnalystService:
    def __init__(self, analytics_service: AnalyticsService, client: OllamaClient) -> None:
        self.analytics_service = analytics_service
        self.client = client

    def get_status(self) -> OllamaStatus:
        return self.client.healthcheck()

    def parse_intent(self, question: str, current_scope: dict) -> ParsedIntentResult:
        messages = [
            LLMMessage(role="system", content=INTENT_SYSTEM_PROMPT),
            LLMMessage(
                role="user",
                content=(
                    "Current deterministic scope:\n"
                    f"{json.dumps(current_scope, indent=2, ensure_ascii=True)}\n\n"
                    f"Question:\n{question}"
                ),
            ),
        ]
        result = self.client.structured_chat(messages=messages, response_model=AnalysisIntent)
        return ParsedIntentResult(
            intent=result.parsed,
            duration_seconds=result.duration_seconds,
            raw_content=result.raw_content,
        )

    def explain_result(self, question: str, result_payload: dict) -> tuple[AIExplanation, float, str]:
        messages = [
            LLMMessage(role="system", content=EXPLANATION_SYSTEM_PROMPT),
            LLMMessage(
                role="user",
                content=(
                    f"Original question:\n{question}\n\n"
                    "Deterministic analytical result payload:\n"
                    f"{json.dumps(result_payload, indent=2, ensure_ascii=True)}"
                ),
            ),
        ]
        result = self.client.structured_chat(messages=messages, response_model=AIExplanation)
        return result.parsed, result.duration_seconds, result.raw_content

    def answer_question(self, question: str, current_scope: dict) -> AnalystResult:
        parsed_intent = self.parse_intent(question=question, current_scope=current_scope)
        dispatch = execute_intent(parsed_intent.intent, self.analytics_service)
        explanation, explanation_duration, _ = self.explain_result(question=question, result_payload=dispatch.payload)
        return AnalystResult(
            intent=parsed_intent.intent,
            result_payload=dispatch.payload,
            explanation=explanation,
            model=self.client.model,
            duration_seconds=parsed_intent.duration_seconds + explanation_duration,
        )


def create_ai_analyst_service(db_path: Path, host: str, model: str, timeout_seconds: int) -> AIAnalystService:
    analytics_service = AnalyticsService(db_path)
    client = OllamaClient(host=host, model=model, timeout_seconds=timeout_seconds)
    return AIAnalystService(analytics_service=analytics_service, client=client)
