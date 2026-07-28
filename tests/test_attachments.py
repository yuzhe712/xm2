from __future__ import annotations

import hashlib

from fastapi.testclient import TestClient

from intelliticket_backend.main import app


def _login(username: str, password: str) -> dict[str, str]:
    response = TestClient(app).post(
        "/api/v1/auth/login",
        json={"user_id": username, "password": password},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['token']}"}


def _submit(headers: dict[str, str]) -> str:
    response = TestClient(app).post(
        "/api/v1/tickets/submit",
        headers=headers,
        json={
            "title": "附件权限测试",
            "text": "请查看随工单上传的日志文件。",
            "desk_id": "support",
            "priority": "P3",
        },
    )
    assert response.status_code == 200
    return response.json()["ticket_id"]


def test_owner_can_upload_list_and_download_attachment() -> None:
    client = TestClient(app)
    owner = _login("wangwu", "wangwu123456")
    ticket_id = _submit(owner)
    content = b"service startup failed\nconnection refused\n"

    uploaded = client.post(
        f"/api/v1/tickets/{ticket_id}/attachments",
        headers=owner,
        files={"file": ("service.log", content, "text/plain")},
    )

    assert uploaded.status_code == 201
    body = uploaded.json()
    assert body["original_name"] == "service.log"
    assert body["size_bytes"] == len(content)
    assert body["sha256"] == hashlib.sha256(content).hexdigest()

    listed = client.get(f"/api/v1/tickets/{ticket_id}/attachments", headers=owner)
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()["items"]] == [body["id"]]

    downloaded = client.get(
        f"/api/v1/tickets/{ticket_id}/attachments/{body['id']}",
        headers=owner,
    )
    assert downloaded.status_code == 200
    assert downloaded.content == content
    assert "service.log" in downloaded.headers["content-disposition"]


def test_other_employee_cannot_list_or_download_attachment() -> None:
    client = TestClient(app)
    owner = _login("wangwu", "wangwu123456")
    other = _login("zhaoliu", "zhaoliu123456")
    ticket_id = _submit(owner)
    uploaded = client.post(
        f"/api/v1/tickets/{ticket_id}/attachments",
        headers=owner,
        files={"file": ("details.txt", b"private ticket details", "text/plain")},
    ).json()

    listed = client.get(f"/api/v1/tickets/{ticket_id}/attachments", headers=other)
    downloaded = client.get(
        f"/api/v1/tickets/{ticket_id}/attachments/{uploaded['id']}",
        headers=other,
    )

    assert listed.status_code == 403
    assert downloaded.status_code == 403


def test_attachment_rejects_extension_mime_and_signature_mismatch() -> None:
    client = TestClient(app)
    owner = _login("wangwu", "wangwu123456")
    ticket_id = _submit(owner)

    executable = client.post(
        f"/api/v1/tickets/{ticket_id}/attachments",
        headers=owner,
        files={"file": ("payload.exe", b"MZ", "application/octet-stream")},
    )
    fake_pdf = client.post(
        f"/api/v1/tickets/{ticket_id}/attachments",
        headers=owner,
        files={"file": ("report.pdf", b"not really a PDF", "application/pdf")},
    )

    assert executable.status_code == 415
    assert executable.json()["error"]["code"] == "ATTACHMENT_TYPE_NOT_ALLOWED"
    assert fake_pdf.status_code == 415
    assert fake_pdf.json()["error"]["code"] == "ATTACHMENT_SIGNATURE_INVALID"
