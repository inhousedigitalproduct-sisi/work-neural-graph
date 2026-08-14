from __future__ import annotations

import json
import socket
from dataclasses import dataclass
from time import perf_counter
from urllib import error, request

from pydantic import BaseModel, ValidationError

from src.llm.models import LLMMessage


class OllamaError(RuntimeError):
    pass


class OllamaUnavailableError(OllamaError):
    pass


class OllamaTimeoutError(OllamaError):
    pass


class OllamaModelNotFoundError(OllamaError):
    pass


class OllamaMalformedResponseError(OllamaError):
    pass


@dataclass(frozen=True)
class OllamaStatus:
    available: bool
    host: str
    model: str
    message: str
    installed_models: tuple[str, ...] = ()


@dataclass(frozen=True)
class StructuredChatResult:
    parsed: BaseModel
    raw_content: str
    duration_seconds: float


class OllamaClient:
    def __init__(self, host: str, model: str, timeout_seconds: int = 60) -> None:
        self.host = host.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds

    def healthcheck(self) -> OllamaStatus:
        try:
            models = self.list_models()
        except OllamaModelNotFoundError as exc:
            return OllamaStatus(False, self.host, self.model, str(exc), ())
        except OllamaError as exc:
            return OllamaStatus(False, self.host, self.model, str(exc), ())

        matched_model = self._resolve_model_name(models)
        if matched_model is None:
            return OllamaStatus(
                available=False,
                host=self.host,
                model=self.model,
                message=f"Configured model '{self.model}' was not found in Ollama.",
                installed_models=tuple(models),
            )

        return OllamaStatus(
            available=True,
            host=self.host,
            model=matched_model,
            message="Ollama is available.",
            installed_models=tuple(models),
        )

    def list_models(self) -> list[str]:
        payload = self._request_json("GET", "/api/tags")
        models = payload.get("models", [])
        if not isinstance(models, list):
            raise OllamaMalformedResponseError("Ollama model list response was malformed.")
        return [item.get("name", "") for item in models if isinstance(item, dict) and item.get("name")]

    def chat(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.0,
        response_format: dict | None = None,
    ) -> tuple[str, float]:
        model_name = self._model_for_request()
        body = {
            "model": model_name,
            "stream": False,
            "messages": [message.model_dump() for message in messages],
            "options": {"temperature": temperature, "num_predict": 700},
            "think": False,
        }
        if response_format is not None:
            body["format"] = response_format
        started = perf_counter()
        payload = self._request_json("POST", "/api/chat", body)
        duration = perf_counter() - started
        try:
            content = payload["message"]["content"]
        except (KeyError, TypeError) as exc:
            raise OllamaMalformedResponseError("Ollama chat response was malformed.") from exc
        if not isinstance(content, str):
            raise OllamaMalformedResponseError("Ollama chat response did not contain text content.")
        return content, duration

    def structured_chat(
        self,
        messages: list[LLMMessage],
        response_model: type[BaseModel],
        temperature: float = 0.0,
    ) -> StructuredChatResult:
        raw_content, duration = self.chat(
            messages=messages,
            temperature=temperature,
            response_format=response_model.model_json_schema(),
        )
        try:
            parsed = response_model.model_validate_json(raw_content)
        except ValidationError as exc:
            raise OllamaMalformedResponseError("Ollama returned invalid structured JSON.") from exc
        return StructuredChatResult(parsed=parsed, raw_content=raw_content, duration_seconds=duration)

    def _request_json(self, method: str, path: str, body: dict | None = None) -> dict:
        data = None
        headers = {"Content-Type": "application/json"}
        if body is not None:
            data = json.dumps(body).encode("utf-8")

        req = request.Request(f"{self.host}{path}", data=data, method=method, headers=headers)
        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as response:
                payload = response.read().decode("utf-8")
        except error.HTTPError as exc:
            if exc.code == 404:
                raise OllamaModelNotFoundError("Configured Ollama endpoint or model was not found.") from exc
            raise OllamaUnavailableError(f"Ollama request failed with HTTP {exc.code}.") from exc
        except error.URLError as exc:
            if isinstance(exc.reason, socket.timeout):
                raise OllamaTimeoutError("Ollama request timed out.") from exc
            raise OllamaUnavailableError(
                "Ollama is currently unavailable at the configured local endpoint."
            ) from exc
        except TimeoutError as exc:
            raise OllamaTimeoutError("Ollama request timed out.") from exc

        try:
            return json.loads(payload)
        except json.JSONDecodeError as exc:
            raise OllamaMalformedResponseError("Ollama returned malformed JSON.") from exc

    def _resolve_model_name(self, installed_models: list[str]) -> str | None:
        if self.model in installed_models:
            return self.model
        prefixed_match = next((name for name in installed_models if name.startswith(f"{self.model}:")), None)
        return prefixed_match

    def _model_for_request(self) -> str:
        try:
            installed_models = self.list_models()
        except OllamaError:
            return self.model
        return self._resolve_model_name(installed_models) or self.model
