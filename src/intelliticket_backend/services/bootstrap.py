from __future__ import annotations

from sqlalchemy.orm import Session

from intelliticket_backend.config import Settings, get_settings
from intelliticket_backend.db import session_scope
from intelliticket_backend.repositories.user_repository import UserRepository
from intelliticket_backend.schemas.users import UserRole


def bootstrap_admin(settings: Settings | None = None, session: Session | None = None) -> bool:
    settings = settings or get_settings()
    username = (settings.bootstrap_admin_username or "").strip()
    password = (
        settings.bootstrap_admin_password.get_secret_value()
        if settings.bootstrap_admin_password is not None
        else ""
    )
    if not username or not password:
        return False

    if session is not None:
        return _create_if_missing(UserRepository(session), settings, username, password)
    with session_scope() as managed_session:
        return _create_if_missing(
            UserRepository(managed_session), settings, username, password
        )


def _create_if_missing(
    repository: UserRepository,
    settings: Settings,
    username: str,
    password: str,
) -> bool:
    if repository.get(username) is not None:
        return False
    repository.create(
        username=username,
        display_name=settings.bootstrap_admin_display_name,
        role=UserRole.ADMIN,
        password=password,
    )
    return True
