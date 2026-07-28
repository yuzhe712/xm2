from __future__ import annotations

from fastapi import APIRouter, Depends, Path, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from intelliticket_backend.db import get_db
from intelliticket_backend.errors import AppError
from intelliticket_backend.repositories.user_repository import UserRepository
from intelliticket_backend.schemas.users import (
    CurrentUser,
    User,
    UserCreateRequest,
    UserResponse,
    UserUpdateRequest,
)
from intelliticket_backend.services.auth import require_admin, require_auth

router = APIRouter(prefix="/api/v1/users", tags=["users"])


def _response(user: User) -> UserResponse:
    return UserResponse(
        id=user.id or "",
        username=user.user_id,
        display_name=user.name,
        role=user.role,
        team_id=user.team_id,
        is_active=user.is_active,
    )


@router.get("/me", response_model=UserResponse)
def get_me(user: CurrentUser = Depends(require_auth)) -> UserResponse:  # noqa: B008
    return UserResponse(
        id=user.id or "",
        username=user.user_id,
        display_name=user.name,
        role=user.role,
        team_id=user.team_id,
        is_active=True,
    )


@router.get("", response_model=list[UserResponse])
def list_users(
    _admin: CurrentUser = Depends(require_admin),  # noqa: B008
    session: Session = Depends(get_db),  # noqa: B008
) -> list[UserResponse]:
    return [_response(user) for user in UserRepository(session).list_all()]


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(
    request: UserCreateRequest,
    _admin: CurrentUser = Depends(require_admin),  # noqa: B008
    session: Session = Depends(get_db),  # noqa: B008
) -> UserResponse:
    try:
        user = UserRepository(session).create(
            username=request.username,
            display_name=request.display_name,
            role=request.role,
            password=request.password,
            team_id=request.team_id,
        )
    except (IntegrityError, ValueError) as exc:
        session.rollback()
        raise AppError("USER_CREATE_FAILED", "无法创建用户", 409, {}) from exc
    return _response(user)


@router.patch("/{user_id}", response_model=UserResponse)
def update_user(
    user_id: str = Path(min_length=1, max_length=36),
    request: UserUpdateRequest = ...,  # type: ignore[assignment]
    _admin: CurrentUser = Depends(require_admin),  # noqa: B008
    session: Session = Depends(get_db),  # noqa: B008
) -> UserResponse:
    try:
        user = UserRepository(session).update(
            user_id,
            display_name=request.display_name,
            role=request.role,
            password=request.password,
            team_id=request.team_id,
            is_active=request.is_active,
        )
    except (IntegrityError, ValueError) as exc:
        session.rollback()
        raise AppError("USER_UPDATE_FAILED", "无法更新用户", 409, {}) from exc
    if user is None:
        raise AppError("USER_NOT_FOUND", "用户不存在", 404, {"user_id": user_id})
    return _response(user)
