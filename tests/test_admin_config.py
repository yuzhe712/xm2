from __future__ import annotations

from fastapi.testclient import TestClient

from intelliticket_backend.main import app


def _login(username: str, password: str) -> dict[str, str]:
    response = TestClient(app).post(
        "/api/v1/auth/login",
        json={"user_id": username, "password": password},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['token']}"}


def test_admin_manages_team_sla_and_service_catalog() -> None:
    client = TestClient(app)
    admin = _login("testadmin", "admin-test-password")

    team = client.post(
        "/api/v1/teams",
        headers=admin,
        json={"code": "ops-p3", "name": "P3 运维组"},
    )
    assert team.status_code == 201

    policy = client.post(
        "/api/v1/sla-policies",
        headers=admin,
        json={
            "name": "P4 test policy",
            "priority": "P4",
            "response_minutes": 480,
            "resolution_minutes": 4320,
        },
    )
    assert policy.status_code == 201

    service = client.post(
        "/api/v1/service-catalog",
        headers=admin,
        json={
            "service_key": "internal-access-p3",
            "name": "内部访问服务",
            "description": "内部系统账号与访问问题",
            "desk_id": "support",
            "team_id": team.json()["id"],
            "keywords": ["VPN", "账号", "VPN"],
            "default_category": "access",
        },
    )
    assert service.status_code == 201
    assert service.json()["keywords"] == ["VPN", "账号"]

    updated = client.patch(
        f"/api/v1/service-catalog/{service.json()['id']}",
        headers=admin,
        json={"is_active": False},
    )
    assert updated.status_code == 200
    assert updated.json()["is_active"] is False

    assert len(client.get("/api/v1/teams", headers=admin).json()) >= 1
    assert len(client.get("/api/v1/sla-policies", headers=admin).json()) >= 1
    assert len(client.get("/api/v1/service-catalog", headers=admin).json()) >= 1


def test_non_admin_cannot_read_or_change_admin_configuration() -> None:
    client = TestClient(app)
    operator = _login("zhangsan", "zhangsan123")
    employee = _login("wangwu", "wangwu123456")

    for headers in (operator, employee):
        assert client.get("/api/v1/teams", headers=headers).status_code == 403
        assert client.get("/api/v1/sla-policies", headers=headers).status_code == 403
        assert client.get("/api/v1/service-catalog", headers=headers).status_code == 403
