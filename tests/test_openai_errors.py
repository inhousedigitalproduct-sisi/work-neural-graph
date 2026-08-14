from __future__ import annotations

from src.llm.client import _describe_openai_error


class RateLimitError(Exception):
    def __init__(self, message: str, code: str = "") -> None:
        super().__init__(message)
        self.code = code


class AuthenticationError(Exception):
    pass


class APITimeoutError(Exception):
    pass


def test_openai_quota_error_explains_billing_and_qwen_fallback() -> None:
    message = _describe_openai_error(
        RateLimitError("You exceeded your current quota", code="insufficient_quota")
    )

    assert "Kuota/billing" in message
    assert "Qwen Local" in message
    assert "insufficient_quota" in message


def test_openai_transient_rate_limit_suggests_retry_or_qwen() -> None:
    message = _describe_openai_error(RateLimitError("Too many requests"))

    assert "rate limit" in message
    assert "Coba lagi" in message
    assert "Qwen Local" in message


def test_openai_authentication_error_is_actionable() -> None:
    message = _describe_openai_error(AuthenticationError("invalid api key"))

    assert "Autentikasi OpenAI gagal" in message
    assert "API key" in message


def test_openai_timeout_error_is_actionable() -> None:
    message = _describe_openai_error(APITimeoutError("request timed out"))

    assert "batas waktu" in message
    assert "Qwen Local" in message
