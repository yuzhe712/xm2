from __future__ import annotations

from intelliticket_backend.config import Settings, get_settings


def test_deepseek_settings_load_from_environment(monkeypatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("LLM_MODEL", "deepseek-chat")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")

    settings = get_settings()

    assert settings.llm_provider == "deepseek"
    assert settings.llm_model == "deepseek-chat"
    assert settings.deepseek_base_url == "https://api.deepseek.com"
    assert settings.deepseek_api_key is not None
    assert settings.deepseek_api_key.get_secret_value() == "sk-test"
    assert settings.resolved_deepseek_api_key is not None
    assert settings.resolved_deepseek_api_key.get_secret_value() == "sk-test"

    get_settings.cache_clear()


def test_deepseek_key_can_load_from_secret_file(tmp_path, monkeypatch) -> None:
    get_settings.cache_clear()
    secret_file = tmp_path / "secrets.toml"
    secret_file.write_text(
        '[llm.deepseek]\napi_key = "sk-from-secret-file"\n',
        encoding="utf-8",
    )
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setenv("INTELLITICKET_SECRET_FILE", str(secret_file))

    settings = get_settings()

    assert settings.resolved_deepseek_api_key is not None
    assert settings.resolved_deepseek_api_key.get_secret_value() == "sk-from-secret-file"

    get_settings.cache_clear()


def test_missing_secret_file_keeps_deepseek_key_unconfigured(tmp_path) -> None:
    settings = Settings(intelliticket_secret_file=tmp_path / "missing.toml")

    assert settings.resolved_deepseek_api_key is None


def test_llm_and_orchestrator_settings_load_from_environment(monkeypatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "3.5")
    monkeypatch.setenv("LLM_MAX_RETRIES", "4")
    monkeypatch.setenv("LLM_RETRY_BACKOFF_SECONDS", "0.25")
    monkeypatch.setenv("LLM_TEMPERATURE", "0.1")
    monkeypatch.setenv("ORCHESTRATOR_MAX_STEPS", "9")
    monkeypatch.setenv("ORCHESTRATOR_ROUTE_MODE", "llm")

    settings = get_settings()

    assert settings.llm_timeout_seconds == 3.5
    assert settings.llm_max_retries == 4
    assert settings.llm_retry_backoff_seconds == 0.25
    assert settings.llm_temperature == 0.1
    assert settings.orchestrator_max_steps == 9
    assert settings.orchestrator_route_mode == "llm"

    get_settings.cache_clear()


def test_ticket_history_db_path_loads_from_environment(tmp_path, monkeypatch) -> None:
    get_settings.cache_clear()
    db_path = tmp_path / "history.sqlite3"
    monkeypatch.setenv("TICKET_HISTORY_DB_PATH", str(db_path))

    settings = get_settings()

    assert settings.ticket_history_db_path == db_path

    get_settings.cache_clear()


def test_feishu_knowledge_settings_load_from_environment(monkeypatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("KNOWLEDGE_PROVIDER", "feishu")
    monkeypatch.setenv("FEISHU_APP_ID", "cli_test_app")
    monkeypatch.setenv("FEISHU_APP_SECRET", "cli_test_secret")
    monkeypatch.setenv("FEISHU_WIKI_SPACE_ID", "spc-test")
    monkeypatch.setenv("FEISHU_DRIVE_FOLDER_URL", "https://my.feishu.cn/drive/folder/fld-test")
    monkeypatch.setenv("FEISHU_DRIVE_FOLDER_TOKEN", "fld-token-test")
    monkeypatch.setenv("FEISHU_TIMEOUT_SECONDS", "2.5")
    monkeypatch.setenv("FEISHU_MAX_RESULTS", "3")

    settings = get_settings()

    assert settings.knowledge_provider == "feishu"
    assert settings.feishu_app_id is not None
    assert settings.feishu_app_id.get_secret_value() == "cli_test_app"
    assert settings.feishu_app_secret is not None
    assert settings.feishu_app_secret.get_secret_value() == "cli_test_secret"
    assert settings.feishu_wiki_space_id == "spc-test"
    assert settings.feishu_drive_folder_url == "https://my.feishu.cn/drive/folder/fld-test"
    assert settings.feishu_drive_folder_token == "fld-token-test"
    assert settings.feishu_timeout_seconds == 2.5
    assert settings.feishu_max_results == 3

    get_settings.cache_clear()


def test_frontend_allowed_origins_load_from_environment(monkeypatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv(
        "FRONTEND_ALLOWED_ORIGINS",
        '["http://127.0.0.1:5173","http://ops-workbench.internal:5173"]',
    )

    settings = get_settings()

    assert settings.frontend_allowed_origins == [
        "http://127.0.0.1:5173",
        "http://ops-workbench.internal:5173",
    ]

    get_settings.cache_clear()
