from __future__ import annotations

import base64
import hmac
import time

from fastapi import Depends, Header, status
from sqlalchemy.orm import Session

from intelliticket_backend.config import get_settings
from intelliticket_backend.db import get_db
from intelliticket_backend.errors import AppError
from intelliticket_backend.repositories.user_repository import UserRepository
from intelliticket_backend.schemas.users import (
    CurrentUser,
    LoginRequest,
    LoginResponse,
    verify_password,
)

_TOKEN_TTL_SECONDS = 24 * 3600


def _signing_key() -> bytes:
    return get_settings().jwt_secret_key.get_secret_value().encode()


def generate_token(user_id: str, name: str = "", role: str = "") -> str:
    del name, role
    expiry = int(time.time()) + _TOKEN_TTL_SECONDS
    payload = f"{user_id}|{expiry}"
    signature = hmac.new(_signing_key(), payload.encode(), "sha256").hexdigest()
    return base64.urlsafe_b64encode(f"{payload}|{signature}".encode()).decode().rstrip("=")


def _token_subject(token: str) -> str | None:
    try:
        padded = token + "=" * (-len(token) % 4)
        raw = base64.urlsafe_b64decode(padded.encode()).decode()
        payload, signature = raw.rsplit("|", 1)
        expected_signature = hmac.new(_signing_key(), payload.encode(), "sha256").hexdigest()
        if not hmac.compare_digest(signature, expected_signature):
            return None
        user_id, expiry_text = payload.split("|", 1)
        if int(expiry_text) < int(time.time()):
            return None
        return user_id
    except (ValueError, UnicodeDecodeError):
        return None


def current_user_from_token(
    token: str,
    repository: UserRepository | None = None,
) -> CurrentUser | None:
    user_id = _token_subject(token)
    if user_id is None:
        return None
    user = (repository or UserRepository()).get_by_id(user_id)
    if user is None or not user.is_active:
        return None
    return CurrentUser(
        id=user.id,
        user_id=user.user_id,
        name=user.name,
        role=user.role,
        team_id=user.team_id,
    )


def verify_token(token: str) -> CurrentUser | None:
    return current_user_from_token(token)


def authenticate(login: LoginRequest, session: Session | None = None) -> LoginResponse:
    user = UserRepository(session).get(login.user_id)
    if (
        user is None
        or not user.is_active
        or not verify_password(login.password, user.password_hash)
    ):
        raise AppError(
            "AUTH_INVALID_CREDENTIALS",
            "用户名或密码错误",
            status.HTTP_401_UNAUTHORIZED,
            {},
        )
    token = generate_token(user.id or "")
    return LoginResponse(
        token=token,
        user_id=user.user_id,
        name=user.name,
        role=user.role,
    )


def require_auth(
    authorization: str = Header(default=""),
    session: Session = Depends(get_db),  # noqa: B008
) -> CurrentUser:
    if not authorization.startswith("Bearer "):
        raise AppError("AUTH_REQUIRED", "请先登录", status.HTTP_401_UNAUTHORIZED, {})
    token = authorization.removeprefix("Bearer ").strip()
    user = current_user_from_token(token, UserRepository(session))
    if user is None:
        raise AppError(
            "AUTH_INVALID_TOKEN",
            "登录已过期，请重新登录",
            status.HTTP_401_UNAUTHORIZED,
            {},
        )
    return user


def require_operator(user: CurrentUser = Depends(require_auth)) -> CurrentUser:  # noqa: B008
    if user.role not in {"operator", "admin"}:
        raise AppError("AUTH_FORBIDDEN", "仅运维人员可执行此操作", 403, {})
    return user


def require_admin(user: CurrentUser = Depends(require_auth)) -> CurrentUser:  # noqa: B008
    if user.role != "admin":
        raise AppError("AUTH_FORBIDDEN", "仅管理员可执行此操作", 403, {})
    return user
