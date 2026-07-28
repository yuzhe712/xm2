from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

from pydantic import BaseModel, Field


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 600_000)
    combined = salt + dk
    return base64.urlsafe_b64encode(combined).decode().rstrip("=")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        padded = password_hash + "=" * (4 - len(password_hash) % 4)
        combined = base64.urlsafe_b64decode(padded.encode())
        salt = combined[:16]
        stored_dk = combined[16:]
        computed_dk = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), salt, 600_000
        )
        return hmac.compare_digest(stored_dk, computed_dk)
    except Exception:
        return False


class UserRole:
    EMPLOYEE = "employee"
    OPERATOR = "operator"
    ADMIN = "admin"
    VALUES = {EMPLOYEE, OPERATOR, ADMIN}


class User(BaseModel):
    id: str | None = None
    user_id: str
    name: str = Field(..., min_length=1, max_length=60)
    role: str = Field(default=UserRole.EMPLOYEE)
    password_hash: str
    dingtalk_user_id: str | None = None
    team_id: str | None = None
    is_active: bool = True


class LoginRequest(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=60)
    password: str = Field(..., min_length=1, max_length=128)


class LoginResponse(BaseModel):
    token: str
    user_id: str
    name: str
    role: str


class CurrentUser(BaseModel):
    """数据库回查后得到的当前有效用户。"""

    id: str | None = None
    user_id: str
    name: str
    role: str
    team_id: str | None = None


class UserResponse(BaseModel):
    id: str
    username: str
    display_name: str
    role: str
    team_id: str | None = None
    is_active: bool


class UserCreateRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=60)
    display_name: str = Field(..., min_length=1, max_length=60)
    role: str = Field(default=UserRole.EMPLOYEE)
    password: str = Field(..., min_length=12, max_length=128)
    team_id: str | None = None


class UserUpdateRequest(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=60)
    role: str | None = None
    password: str | None = Field(default=None, min_length=12, max_length=128)
    team_id: str | None = None
    is_active: bool | None = None
