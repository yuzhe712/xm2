from __future__ import annotations

import tomllib
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用配置。"""

    app_name: str = "IntelliTicket Backend"
    app_version: str = "0.1.0"
    data_mode: str = "mock"
    mock_data_dir: Path = Field(default=Path("mock_data"))
    llm_provider: str = "deepseek"
    llm_model: str = "deepseek-chat"
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_api_key: SecretStr | None = None
    llm_timeout_seconds: float = Field(default=10.0, gt=0)
    llm_max_retries: int = Field(default=2, ge=0)
    llm_retry_backoff_seconds: float = Field(default=0.5, ge=0)
    llm_temperature: float | None = Field(default=0.0, ge=0.0, le=2.0)
    orchestrator_max_steps: int = Field(default=8, ge=1)
    orchestrator_route_mode: str = "deterministic"
    support_workflow_strategy: str = "deterministic"
    intake_agent_strategy: str = "deterministic"
    diagnosis_agent_strategy: str = "deterministic"
    support_reply_agent_strategy: str = "deterministic"
    frontend_allowed_origins: list[str] = Field(
        default_factory=lambda: ["http://127.0.0.1:5173", "http://localhost:5173"]
    )
    ticket_history_db_path: Path = Field(default=Path("data/intelliticket.sqlite3"))
    intelliticket_secret_file: Path | None = None
    dingtalk_webhook_url: SecretStr | None = None
    dingtalk_enabled: bool = False
    dingtalk_operator_webhook_url: SecretStr | None = None
    dingtalk_employee_webhook_url: SecretStr | None = None
    knowledge_provider: str = "mock"
    feishu_app_id: SecretStr | None = None
    feishu_app_secret: SecretStr | None = None
    feishu_base_url: str = "https://open.feishu.cn"
    feishu_wiki_space_id: str | None = None
    feishu_drive_folder_url: str | None = None
    feishu_drive_folder_token: str | None = None
    feishu_timeout_seconds: float = Field(default=5.0, gt=0)
    feishu_max_results: int = Field(default=5, ge=1, le=20)

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @property
    def service_name(self) -> str:
        return "intelliticket-backend"

    @property
    def resolved_deepseek_api_key(self) -> SecretStr | None:
        if self.deepseek_api_key and self.deepseek_api_key.get_secret_value().strip():
            return self.deepseek_api_key
        secret_value = self._deepseek_api_key_from_secret_file()
        if secret_value:
            return SecretStr(secret_value)
        return None

    def _deepseek_api_key_from_secret_file(self) -> str | None:
        if self.intelliticket_secret_file is None:
            return None
        if not self.intelliticket_secret_file.exists():
            return None
        with self.intelliticket_secret_file.open("rb") as file:
            data = tomllib.load(file)
        value = self._nested_get(data, ["llm", "deepseek", "api_key"])
        if isinstance(value, str) and value.strip():
            return value.strip()
        return None

    def _nested_get(self, data: dict[str, Any], keys: list[str]) -> Any | None:
        current: Any = data
        for key in keys:
            if not isinstance(current, dict) or key not in current:
                return None
            current = current[key]
        return current


@lru_cache
def get_settings() -> Settings:
    return Settings()
