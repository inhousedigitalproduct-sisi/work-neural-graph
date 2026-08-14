from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from src.analytics.service import AnalyticsService
from src.llm.client import OllamaClient, OpenAIClient
from src.llm.dispatcher import execute_intent
from src.llm.models import AIExplanation, AnalysisIntent, AnalystResult, LLMMessage
from src.llm.prompts import EXPLANATION_SYSTEM_PROMPT, INTENT_SYSTEM_PROMPT


@dataclass(frozen=True)
class ParsedIntentResult:
    intent: AnalysisIntent
    duration_seconds: float
    raw_content: str


class AIAnalystService:
    def __init__(self, analytics_service: AnalyticsService, client: OpenAIClient | OllamaClient) -> None:
        self.analytics_service = analytics_service
        self.client = client

    def get_status(self):
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


def create_ai_analyst_service(
    db_path: Path,
    provider: str,
    model: str,
    timeout_seconds: int,
    api_key_env: str = "OPENAI_API_KEY",
    ollama_host: str = "http://localhost:11434",
) -> AIAnalystService:
    analytics_service = AnalyticsService(db_path)
    provider_name = provider.strip().lower()

    if provider_name == "openai":
        client = OpenAIClient(
            api_key=os.getenv(api_key_env),
            model=model,
            timeout_seconds=timeout_seconds,
            api_key_env=api_key_env,
        )
    elif provider_name == "ollama":
        client = OllamaClient(
            host=ollama_host,
            model=model,
            timeout_seconds=timeout_seconds,
        )
    else:
        raise ValueError(f"Unsupported LLM provider: {provider}")

    return AIAnalystService(analytics_service=analytics_service, client=client)
