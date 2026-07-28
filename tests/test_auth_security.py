from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from intelliticket_backend.config import DEVELOPMENT_JWT_SECRET, Settings
from intelliticket_backend.db import get_engine, session_scope
from intelliticket_backend.main import app
from intelliticket_backend.models import Base
from intelliticket_backend.repositories.user_repository import UserRepository
from intelliticket_backend.services.bootstrap import bootstrap_admin


def _login(username: str, password: str) -> dict[str, str]:
    response = TestClient(app).post(
        "/api/v1/auth/login",
        json={"user_id": username, "password": password},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['token']}"}


def test_disabled_user_old_token_is_rejected_immediately() -> None:
    headers = _login("zhaoliu", "zhaoliu123456")
    with session_scope() as session:
        repository = UserRepository(session)
        user = repository.get("zhaoliu")
        assert user is not None and user.id is not None
        repository.update(user.id, is_active=False)

    try:
        response = TestClient(app).get("/api/v1/users/me", headers=headers)
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "AUTH_INVALID_TOKEN"
    finally:
        with session_scope() as session:
            repository = UserRepository(session)
            user = repository.get("zhaoliu")
            assert user is not None and user.id is not None
            repository.update(user.id, is_active=True)


def test_bootstrap_admin_is_database_backed_and_idempotent(tmp_path) -> None:
    database_url = f"sqlite+pysqlite:///{(tmp_path / 'bootstrap.sqlite3').as_posix()}"
    engine = get_engine(database_url)
    Base.metadata.create_all(engine)
    settings = Settings(
        _env_file=None,
        app_env="test",
        database_url=database_url,
        jwt_secret_key="test-bootstrap-jwt-secret-at-least-32-characters",
        bootstrap_admin_username="first-admin",
        bootstrap_admin_password="unique-bootstrap-password",
    )

    with session_scope(database_url) as session:
        assert bootstrap_admin(settings, session) is True
        assert bootstrap_admin(settings, session) is False
        user = UserRepository(session).get("first-admin")
        assert user is not None
        assert user.role == "admin"
        assert user.is_active is True


def test_production_rejects_default_jwt_secret() -> None:
    with pytest.raises(ValidationError, match="non-default JWT_SECRET_KEY"):
        Settings(
            _env_file=None,
            app_env="production",
            database_url="postgresql+psycopg://app:secret@db/intelliticket",
            jwt_secret_key=DEVELOPMENT_JWT_SECRET,
        )


def test_production_rejects_unsafe_bootstrap_password() -> None:
    with pytest.raises(ValidationError, match="unsafe bootstrap"):
        Settings(
            _env_file=None,
            app_env="production",
            database_url="postgresql+psycopg://app:secret@db/intelliticket",
            jwt_secret_key="production-jwt-secret-that-is-long-and-random-enough",
            bootstrap_admin_username="admin",
            bootstrap_admin_password="admin",
        )


def test_operator_cannot_call_admin_user_api(operator_auth) -> None:
    response = TestClient(app).get("/api/v1/users", headers=operator_auth)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "AUTH_FORBIDDEN"


def test_admin_can_create_and_disable_user_and_invalidate_token() -> None:
    client = TestClient(app)
    admin_headers = _login("testadmin", "admin-test-password")

    created = client.post(
        "/api/v1/users",
        headers=admin_headers,
        json={
            "username": "api-managed-user",
            "display_name": "API 管理用户",
            "role": "employee",
            "password": "api-managed-password",
        },
    )
    assert created.status_code == 201
    user_id = created.json()["id"]
    user_headers = _login("api-managed-user", "api-managed-password")

    disabled = client.patch(
        f"/api/v1/users/{user_id}",
        headers=admin_headers,
        json={"is_active": False},
    )
    assert disabled.status_code == 200
    assert disabled.json()["is_active"] is False

    rejected = client.get("/api/v1/users/me", headers=user_headers)
    assert rejected.status_code == 401
    assert rejected.json()["error"]["code"] == "AUTH_INVALID_TOKEN"
