from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import select
from sqlalchemy.orm import Session

from intelliticket_backend.db import session_scope
from intelliticket_backend.models.identity import User as UserModel
from intelliticket_backend.schemas.users import User, UserRole, hash_password


class UserRepository:
    """Database-backed user repository."""

    def __init__(self, session: Session | None = None) -> None:
        self.session = session

    @contextmanager
    def _session(self) -> Iterator[Session]:
        if self.session is not None:
            yield self.session
            return
        with session_scope() as session:
            yield session

    def get(self, username: str) -> User | None:
        with self._session() as session:
            model = session.scalar(select(UserModel).where(UserModel.username == username))
            return self._to_schema(model) if model else None

    def get_by_id(self, user_id: str) -> User | None:
        with self._session() as session:
            model = session.get(UserModel, user_id)
            return self._to_schema(model) if model else None

    def list_by_role(self, role: str) -> list[User]:
        with self._session() as session:
            models = session.scalars(
                select(UserModel).where(UserModel.role == role).order_by(UserModel.username)
            ).all()
            return [self._to_schema(model) for model in models]

    def list_all(self) -> list[User]:
        with self._session() as session:
            models = session.scalars(select(UserModel).order_by(UserModel.username)).all()
            return [self._to_schema(model) for model in models]

    def employee_ids(self) -> list[str]:
        return [user.user_id for user in self.list_by_role(UserRole.EMPLOYEE)]

    def create(
        self,
        *,
        username: str,
        display_name: str,
        role: str,
        password: str,
        team_id: str | None = None,
        is_active: bool = True,
    ) -> User:
        if role not in UserRole.VALUES:
            raise ValueError(f"unsupported user role: {role}")
        with self._session() as session:
            model = UserModel(
                username=username.strip(),
                display_name=display_name.strip(),
                role=role,
                password_hash=hash_password(password),
                team_id=team_id,
                is_active=is_active,
            )
            session.add(model)
            session.flush()
            return self._to_schema(model)

    def update(
        self,
        user_id: str,
        *,
        display_name: str | None = None,
        role: str | None = None,
        password: str | None = None,
        team_id: str | None = None,
        is_active: bool | None = None,
    ) -> User | None:
        if role is not None and role not in UserRole.VALUES:
            raise ValueError(f"unsupported user role: {role}")
        with self._session() as session:
            model = session.get(UserModel, user_id)
            if model is None:
                return None
            if display_name is not None:
                model.display_name = display_name.strip()
            if role is not None:
                model.role = role
            if password is not None:
                model.password_hash = hash_password(password)
            if team_id is not None:
                model.team_id = team_id
            if is_active is not None:
                model.is_active = is_active
            session.flush()
            return self._to_schema(model)

    @staticmethod
    def _to_schema(model: UserModel) -> User:
        return User(
            id=model.id,
            user_id=model.username,
            name=model.display_name,
            role=model.role,
            password_hash=model.password_hash,
            team_id=model.team_id,
            is_active=model.is_active,
        )
