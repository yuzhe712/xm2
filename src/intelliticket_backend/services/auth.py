from __future__ import annotations

import base64
import hashlib
import hmac
import time

from fastapi import Depends, Header, status

from intelliticket_backend.config import get_settings
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
    settings = get_settings()
    raw = settings.app_name + settings.app_version + "intelliticket-auth"
    return hashlib.sha256(raw.encode()).digest()


def generate_token(user_id: str, name: str, role: str) -> str:
    expiry = int(time.time()) + _TOKEN_TTL_SECONDS
    payload = f"{user_id}|{name}|{role}|{expiry}"
    sig = hmac.new(_signing_key(), payload.encode(), "sha256").hexdigest()
    token_raw = f"{payload}|{sig}"
    return base64.urlsafe_b64encode(token_raw.encode()).decode().rstrip("=")


def verify_token(token: str) -> CurrentUser | None:
    try:
        padded = token + "=" * (4 - len(token) % 4)
        raw = base64.urlsafe_b64decode(padded.encode()).decode()
        parts = raw.rsplit("|", 1)
        if len(parts) != 2:
            return None
        payload, sig = parts
        expected_sig = hmac.new(
            _signing_key(), payload.encode(), "sha256"
        ).hexdigest()
        if not hmac.compare_digest(sig, expected_sig):
            return None
        user_id, name, role, expiry_str = payload.split("|", 3)
        if int(expiry_str) < int(time.time()):
            return None
        return CurrentUser(user_id=user_id, name=name, role=role)
    except Exception:
        return None


def authenticate(login: LoginRequest) -> LoginResponse:
    user = UserRepository().get(login.user_id)
    if user is None:
        raise AppError(
            "AUTH_INVALID_CREDENTIALS",
            "用户名或密码错误",
            status.HTTP_401_UNAUTHORIZED,
            {},
        )
    if not verify_password(login.password, user.password_hash):
        raise AppError(
            "AUTH_INVALID_CREDENTIALS",
            "用户名或密码错误",
            status.HTTP_401_UNAUTHORIZED,
            {},
        )
    token = generate_token(user.user_id, user.name, user.role)
    return LoginResponse(
        token=token,
        user_id=user.user_id,
        name=user.name,
        role=user.role,
    )


def require_auth(authorization: str = Header(default="")) -> CurrentUser:
    if not authorization.startswith("Bearer "):
        raise AppError(
            "AUTH_REQUIRED",
            "请先登录",
            status.HTTP_401_UNAUTHORIZED,
            {},
        )
    token = authorization.removeprefix("Bearer ").strip()
    user = verify_token(token)
    if user is None:
        raise AppError(
            "AUTH_INVALID_TOKEN",
            "登录已过期，请重新登录",
            status.HTTP_401_UNAUTHORIZED,
            {},
        )
    return user


def require_operator(
    user: CurrentUser = Depends(require_auth),  # noqa: B008
) -> CurrentUser:
    if user.role != "operator":
        raise AppError(
            "AUTH_FORBIDDEN",
            "仅运维人员可执行此操作",
            status.HTTP_403_FORBIDDEN,
            {},
        )
    return user
