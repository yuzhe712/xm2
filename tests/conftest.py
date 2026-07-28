from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest


def pytest_configure() -> None:
    """测试运行时强制 deterministic 策略，避免依赖 .env 中的 LLM 配置。"""
    os.environ.setdefault("INTAKE_AGENT_STRATEGY", "deterministic")
    os.environ.setdefault("DIAGNOSIS_AGENT_STRATEGY", "deterministic")
    os.environ.setdefault("SUPPORT_REPLY_AGENT_STRATEGY", "deterministic")
    auth_db = Path(tempfile.gettempdir()) / f"intelliticket-auth-tests-{os.getpid()}.sqlite3"
    os.environ["APP_ENV"] = "test"
    os.environ["DATABASE_URL"] = f"sqlite+pysqlite:///{auth_db.as_posix()}"
    os.environ["JWT_SECRET_KEY"] = "test-only-jwt-secret-with-at-least-32-characters"


@pytest.fixture(scope="session", autouse=True)
def auth_database() -> None:
    from intelliticket_backend.db import get_engine, get_session_factory, session_scope
    from intelliticket_backend.models import Base
    from intelliticket_backend.repositories.user_repository import UserRepository

    get_engine.cache_clear()
    get_session_factory.cache_clear()
    engine = get_engine()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    users = [
        ("zhangsan", "张三", "operator", "zhangsan123"),
        ("lisi", "李四", "operator", "lisi12345678"),
        ("wangwu", "王五", "employee", "wangwu123456"),
        ("zhaoliu", "赵六", "employee", "zhaoliu123456"),
        ("testadmin", "测试管理员", "admin", "admin-test-password"),
    ]
    with session_scope() as session:
        repository = UserRepository(session)
        for username, display_name, role, password in users:
            repository.create(
                username=username,
                display_name=display_name,
                role=role,
                password=password,
            )
    yield
    engine.dispose()


@pytest.fixture
def operator_auth(auth_database) -> dict[str, str]:
    from fastapi.testclient import TestClient

    from intelliticket_backend.main import app

    response = TestClient(app).post(
        "/api/v1/auth/login",
        json={"user_id": "zhangsan", "password": "zhangsan123"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['token']}"}
