from __future__ import annotations

import json

import httpx
import pytest
from pydantic import BaseModel, SecretStr

from intelliticket_backend.schemas.orchestration import RouteDecision
from intelliticket_backend.services.llm import DeepSeekChatClient, LlmClientError


class SimpleSchema(BaseModel):
    value: str


def make_client(
    transport: httpx.MockTransport,
    *,
    api_key: SecretStr | None = None,
    max_retries: int = 0,
) -> DeepSeekChatClient:
    resolved_api_key = api_key if api_key is not None else SecretStr("sk-test-secret")
    return DeepSeekChatClient(
        api_key=resolved_api_key,
        base_url="https://api.deepseek.test",
        model="deepseek-chat",
        timeout_seconds=1.0,
        max_retries=max_retries,
        retry_backoff_seconds=0.0,
        http_client=httpx.Client(transport=transport),
    )


def deepseek_response(content: object, status_code: int = 200) -> httpx.Response:
    return httpx.Response(
        status_code,
        json={"choices": [{"message": {"content": content}}]},
    )


def test_missing_key_raises_error_without_secret() -> None:
    client = DeepSeekChatClient(
        api_key=None,
        base_url="https://api.deepseek.test",
        model="deepseek-chat",
        timeout_seconds=1.0,
        max_retries=0,
        retry_backoff_seconds=0.0,
        http_client=httpx.Client(
            transport=httpx.MockTransport(lambda _request: deepseek_response({}))
        ),
    )

    with pytest.raises(LlmClientError) as exc_info:
        client.structured_json_call(
            system_prompt="Return JSON.",
            user_payload={},
            response_schema=RouteDecision,
        )

    assert exc_info.value.code == "LLM_API_KEY_MISSING"
    assert "sk-test" not in str(exc_info.value.details)


def test_http_error_raises_provider_error_without_key_leak() -> None:
    seen_authorization = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal seen_authorization
        seen_authorization = request.headers.get("Authorization")
        return httpx.Response(500, json={"error": "boom"})

    client = make_client(httpx.MockTransport(handler), max_retries=0)

    with pytest.raises(LlmClientError) as exc_info:
        client.structured_json_call(
            system_prompt="Return JSON.",
            user_payload={},
            response_schema=RouteDecision,
        )

    assert seen_authorization == "Bearer sk-test-secret"
    assert exc_info.value.code == "LLM_PROVIDER_ERROR"
    assert "sk-test-secret" not in str(exc_info.value)
    assert "sk-test-secret" not in str(exc_info.value.details)


def test_timeout_retries_and_exhausts_without_key_leak() -> None:
    attempts = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        raise httpx.TimeoutException("timed out")

    client = make_client(httpx.MockTransport(handler), max_retries=1)

    with pytest.raises(LlmClientError) as exc_info:
        client.structured_json_call(
            system_prompt="Return JSON.",
            user_payload={},
            response_schema=RouteDecision,
        )

    assert attempts == 2
    assert exc_info.value.code == "LLM_RETRY_EXHAUSTED"
    assert "sk-test-secret" not in str(exc_info.value.details)


def test_malformed_json_content_raises_invalid_json() -> None:
    client = make_client(httpx.MockTransport(lambda _request: deepseek_response("not json")))

    with pytest.raises(LlmClientError) as exc_info:
        client.structured_json_call(
            system_prompt="Return JSON.",
            user_payload={},
            response_schema=RouteDecision,
        )

    assert exc_info.value.code == "LLM_INVALID_JSON"


def test_schema_invalid_raises_validation_error() -> None:
    client = make_client(
        httpx.MockTransport(lambda _request: deepseek_response(json.dumps({"value": "ok"})))
    )

    with pytest.raises(LlmClientError) as exc_info:
        client.structured_json_call(
            system_prompt="Return JSON.",
            user_payload={},
            response_schema=RouteDecision,
        )

    assert exc_info.value.code == "LLM_SCHEMA_VALIDATION_FAILED"


def test_valid_json_validates_schema() -> None:
    payload = {
        "next_agent": "ticket_intake_agent",
        "message_type": "ticket_intake_request",
        "reason_summary": "先执行 intake。",
    }
    client = make_client(
        httpx.MockTransport(lambda _request: deepseek_response(json.dumps(payload)))
    )

    result = client.structured_json_call(
        system_prompt="Return JSON.",
        user_payload={},
        response_schema=RouteDecision,
    )

    assert result.next_agent == "ticket_intake_agent"
