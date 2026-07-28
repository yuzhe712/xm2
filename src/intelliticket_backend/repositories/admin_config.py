from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from intelliticket_backend.errors import AppError
from intelliticket_backend.models import ServiceCatalogItem, SlaPolicy, Team
from intelliticket_backend.schemas.admin import ServiceCatalogResponse


class AdminConfigRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_teams(self) -> list[Team]:
        return list(self.session.scalars(select(Team).order_by(Team.code)).all())

    def create_team(self, *, code: str, name: str) -> Team:
        team = Team(code=code.strip(), name=name.strip())
        self.session.add(team)
        self.session.flush()
        return team

    def update_team(self, team_id: str, values: dict[str, Any]) -> Team | None:
        team = self.session.get(Team, team_id)
        if team is None:
            return None
        for field, value in values.items():
            setattr(team, field, value.strip() if isinstance(value, str) else value)
        self.session.flush()
        return team

    def list_sla_policies(self) -> list[SlaPolicy]:
        return list(self.session.scalars(select(SlaPolicy).order_by(SlaPolicy.priority)).all())

    def create_sla_policy(self, values: dict[str, Any]) -> SlaPolicy:
        policy = SlaPolicy(**values)
        self.session.add(policy)
        self.session.flush()
        return policy

    def update_sla_policy(self, policy_id: str, values: dict[str, Any]) -> SlaPolicy | None:
        policy = self.session.get(SlaPolicy, policy_id)
        if policy is None:
            return None
        for field, value in values.items():
            setattr(policy, field, value.strip() if isinstance(value, str) else value)
        self.session.flush()
        return policy

    def list_catalog(self) -> list[ServiceCatalogResponse]:
        items = self.session.scalars(
            select(ServiceCatalogItem).order_by(ServiceCatalogItem.name)
        ).all()
        return [self.catalog_response(item) for item in items]

    def create_catalog_item(self, values: dict[str, Any]) -> ServiceCatalogItem:
        self._ensure_team(values.get("team_id"))
        keywords = values.pop("keywords", [])
        item = ServiceCatalogItem(keywords_json=keywords, **values)
        self.session.add(item)
        self.session.flush()
        return item

    def update_catalog_item(
        self, item_id: str, values: dict[str, Any]
    ) -> ServiceCatalogItem | None:
        item = self.session.get(ServiceCatalogItem, item_id)
        if item is None:
            return None
        if "team_id" in values:
            self._ensure_team(values["team_id"])
        if "keywords" in values:
            item.keywords_json = values.pop("keywords")
        for field, value in values.items():
            setattr(item, field, value.strip() if isinstance(value, str) else value)
        self.session.flush()
        return item

    def _ensure_team(self, team_id: str | None) -> None:
        if team_id is None:
            return
        team = self.session.get(Team, team_id)
        if team is None or not team.is_active:
            raise AppError("TEAM_NOT_FOUND", "指定团队不存在或已停用", 404, {})

    @staticmethod
    def catalog_response(item: ServiceCatalogItem) -> ServiceCatalogResponse:
        return ServiceCatalogResponse(
            id=item.id,
            service_key=item.service_key,
            name=item.name,
            description=item.description,
            desk_id=item.desk_id,
            team_id=item.team_id,
            keywords=item.keywords_json,
            default_category=item.default_category,
            is_active=item.is_active,
            created_at=item.created_at,
            updated_at=item.updated_at,
        )
