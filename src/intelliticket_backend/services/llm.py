from __future__ import annotations

import json
import logging
import time
from abc import ABC, abstractmethod
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, SecretStr, ValidationError

logger = logging.getLogger(__name__)

StructuredModel = TypeVar("StructuredModel", bound=BaseModel)


class LlmClientError(Exception):
    """LLM 客户端可预期错误，details 必须保持脱敏。"""

    def __init__(
        self,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.details = details or {}


class LlmClient(ABC):
    """结构化 LLM 调用接口。"""

    @abstractmethod
    def structured_json_call(
        self,
        *,
        system_prompt: str,
        user_payload: dict[str, Any],
        response_schema: type[StructuredModel],
        temperature: float | None = None,
    ) -> StructuredModel:
        """调用 LLM 并返回通过 Pydantic schema 校验的 JSON 对象。"""


class DeepSeekChatClient(LlmClient):
    """DeepSeek chat completions 结构化 JSON 客户端。"""

    def __init__(
        self,
        *,
        api_key: SecretStr | None,
        base_url: str,
        model: str,
        timeout_seconds: float,
        max_retries: int,
        retry_backoff_seconds: float,
        temperature: float | None = 0.0,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.retry_backoff_seconds = retry_backoff_seconds
        self.temperature = temperature
        self.http_client = http_client or httpx.Client(timeout=timeout_seconds)
        self.total_calls = 0
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0

    def structured_json_call(
        self,
        *,
        system_prompt: str,
        user_payload: dict[str, Any],
        response_schema: type[StructuredModel],
        temperature: float | None = None,
    ) -> StructuredModel:
        if self.api_key is None or not self.api_key.get_secret_value().strip():
            raise LlmClientError(
                "LLM_API_KEY_MISSING",
                "DeepSeek API key 未配置",
                {"provider": "deepseek", "model": self.model},
            )

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": json.dumps(user_payload, ensure_ascii=False),
                },
            ],
            "response_format": {"type": "json_object"},
        }
        effective_temperature = self.temperature if temperature is None else temperature
        if effective_temperature is not None:
            payload["temperature"] = effective_temperature

        headers = {
            "Authorization": f"Bearer {self.api_key.get_secret_value()}",
            "Content-Type": "application/json",
        }
        attempts = self.max_retries + 1
        last_error: LlmClientError | None = None
        for attempt in range(1, attempts + 1):
            self.total_calls += 1
            try:
                response = self.http_client.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=self.timeout_seconds,
                )
            except httpx.TimeoutException as exc:
                last_error = LlmClientError(
                    "LLM_TIMEOUT",
                    "DeepSeek 请求超时",
                    {"provider": "deepseek", "model": self.model, "attempt": attempt},
                )
                logger.warning(
                    "DeepSeek request timed out: model=%s attempt=%s",
                    self.model,
                    attempt,
                )
                if attempt < attempts:
                    self._sleep_before_retry(attempt)
                    continue
                raise LlmClientError(
                    "LLM_RETRY_EXHAUSTED",
                    "DeepSeek 请求重试耗尽",
                    {
                        "provider": "deepseek",
                        "model": self.model,
                        "attempts": attempts,
                        "last_error_code": last_error.code,
                    },
                ) from exc
            except httpx.HTTPError as exc:
                raise LlmClientError(
                    "LLM_PROVIDER_ERROR",
                    "DeepSeek HTTP 请求失败",
                    {"provider": "deepseek", "model": self.model, "error_type": type(exc).__name__},
                ) from exc

            if response.status_code >= 500 and attempt < attempts:
                logger.warning(
                    "DeepSeek provider returned retryable status: model=%s status=%s attempt=%s",
                    self.model,
                    response.status_code,
                    attempt,
                )
                self._sleep_before_retry(attempt)
                continue

            if response.status_code < 200 or response.status_code >= 300:
                raise LlmClientError(
                    "LLM_PROVIDER_ERROR",
                    "DeepSeek 返回非成功状态码",
                    {
                        "provider": "deepseek",
                        "model": self.model,
                        "status_code": response.status_code,
                    },
                )

            raw_content = self._extract_content(response)
            parsed = self._parse_json_content(raw_content)
            try:
                return response_schema.model_validate(parsed)
            except ValidationError as exc:
                logger.warning(
                    "LLM schema validation failed: errors=%s raw_keys=%s",
                    exc.errors(),
                    list(parsed.keys()) if isinstance(parsed, dict) else type(parsed),
                )
                raise LlmClientError(
                    "LLM_SCHEMA_VALIDATION_FAILED",
                    "LLM 输出未通过 JSON schema 校验",
                    {
                        "provider": "deepseek",
                        "model": self.model,
                        "error_count": len(exc.errors()),
                        "errors": [
                            {"loc": list(e["loc"]), "msg": e["msg"]}
                            for e in exc.errors()[:5]
                        ],
                    },
                ) from exc

        raise LlmClientError(
            "LLM_RETRY_EXHAUSTED",
            "DeepSeek 请求重试耗尽",
            {"provider": "deepseek", "model": self.model, "attempts": attempts},
        )

    def _extract_content(self, response: httpx.Response) -> Any:
        try:
            body = response.json()
        except ValueError as exc:
            raise LlmClientError(
                "LLM_INVALID_JSON",
                "DeepSeek 响应不是合法 JSON",
                {"provider": "deepseek", "model": self.model},
            ) from exc

        try:
            usage = body.get("usage", {})
            self.total_prompt_tokens += int(usage.get("prompt_tokens", 0) or 0)
            self.total_completion_tokens += int(usage.get("completion_tokens", 0) or 0)
            return body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LlmClientError(
                "LLM_PROVIDER_ERROR",
                "DeepSeek 响应缺少 message content",
                {"provider": "deepseek", "model": self.model},
            ) from exc

    def _parse_json_content(self, raw_content: Any) -> dict[str, Any]:
        if isinstance(raw_content, dict):
            return raw_content
        if not isinstance(raw_content, str):
            raise LlmClientError(
                "LLM_INVALID_JSON",
                "DeepSeek message content 不是 JSON 对象",
                {"provider": "deepseek", "model": self.model},
            )
        try:
            parsed = json.loads(raw_content)
        except ValueError as exc:
            raise LlmClientError(
                "LLM_INVALID_JSON",
                "DeepSeek message content 不是合法 JSON",
                {"provider": "deepseek", "model": self.model},
            ) from exc
        if not isinstance(parsed, dict):
            raise LlmClientError(
                "LLM_INVALID_JSON",
                "DeepSeek message content 不是 JSON 对象",
                {"provider": "deepseek", "model": self.model},
            )
        return parsed

    def _sleep_before_retry(self, attempt: int) -> None:
        if self.retry_backoff_seconds <= 0:
            return
        time.sleep(self.retry_backoff_seconds * attempt)
