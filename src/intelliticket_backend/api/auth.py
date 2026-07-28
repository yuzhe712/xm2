from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from intelliticket_backend.db import get_db
from intelliticket_backend.schemas.users import LoginRequest, LoginResponse
from intelliticket_backend.services.auth import authenticate

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
def login(
    request: LoginRequest,
    session: Session = Depends(get_db),  # noqa: B008
) -> LoginResponse:
    """用户名 + 密码登录，返回认证 token（24 小时有效）。"""
    return authenticate(request, session)
