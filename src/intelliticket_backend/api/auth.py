from __future__ import annotations

from fastapi import APIRouter

from intelliticket_backend.schemas.users import LoginRequest, LoginResponse
from intelliticket_backend.services.auth import authenticate

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
def login(request: LoginRequest) -> LoginResponse:
    """用户名 + 密码登录，返回认证 token（24 小时有效）。"""
    return authenticate(request)
