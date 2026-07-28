from __future__ import annotations

from fastapi import APIRouter, Depends, Path, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from intelliticket_backend.db import get_db
from intelliticket_backend.errors import AppError
from intelliticket_backend.repositories.admin_config import AdminConfigRepository
from intelliticket_backend.schemas.admin import (
    ServiceCatalogCreateRequest,
    ServiceCatalogResponse,
    ServiceCatalogUpdateRequest,
    SlaPolicyCreateRequest,
    SlaPolicyResponse,
    SlaPolicyUpdateRequest,
    TeamCreateRequest,
    TeamResponse,
    TeamUpdateRequest,
)
from intelliticket_backend.schemas.users import CurrentUser
from intelliticket_backend.services.auth import require_admin

router = APIRouter(prefix="/api/v1", tags=["admin-config"])


def _admin_error(exc: IntegrityError) -> AppError:
    return AppError("CONFIG_CONFLICT", "配置标识或名称已存在", 409, {})


@router.get("/teams", response_model=list[TeamResponse])
def list_teams(
    _admin: CurrentUser = Depends(require_admin),  # noqa: B008
    session: Session = Depends(get_db),  # noqa: B008
) -> list[TeamResponse]:
    return [
        TeamResponse.model_validate(item)
        for item in AdminConfigRepository(session).list_teams()
    ]


@router.post("/teams", response_model=TeamResponse, status_code=status.HTTP_201_CREATED)
def create_team(
    request: TeamCreateRequest,
    _admin: CurrentUser = Depends(require_admin),  # noqa: B008
    session: Session = Depends(get_db),  # noqa: B008
) -> TeamResponse:
    try:
        item = AdminConfigRepository(session).create_team(code=request.code, name=request.name)
    except IntegrityError as exc:
        session.rollback()
        raise _admin_error(exc) from exc
    return TeamResponse.model_validate(item)


@router.patch("/teams/{team_id}", response_model=TeamResponse)
def update_team(
    request: TeamUpdateRequest,
    team_id: str = Path(min_length=1, max_length=36),
    _admin: CurrentUser = Depends(require_admin),  # noqa: B008
    session: Session = Depends(get_db),  # noqa: B008
) -> TeamResponse:
    item = AdminConfigRepository(session).update_team(
        team_id, request.model_dump(exclude_unset=True)
    )
    if item is None:
        raise AppError("TEAM_NOT_FOUND", "团队不存在", 404, {"team_id": team_id})
    return TeamResponse.model_validate(item)


@router.get("/sla-policies", response_model=list[SlaPolicyResponse])
def list_sla_policies(
    _admin: CurrentUser = Depends(require_admin),  # noqa: B008
    session: Session = Depends(get_db),  # noqa: B008
) -> list[SlaPolicyResponse]:
    return [
        SlaPolicyResponse.model_validate(item)
        for item in AdminConfigRepository(session).list_sla_policies()
    ]


@router.post(
    "/sla-policies", response_model=SlaPolicyResponse, status_code=status.HTTP_201_CREATED
)
def create_sla_policy(
    request: SlaPolicyCreateRequest,
    _admin: CurrentUser = Depends(require_admin),  # noqa: B008
    session: Session = Depends(get_db),  # noqa: B008
) -> SlaPolicyResponse:
    try:
        item = AdminConfigRepository(session).create_sla_policy(request.model_dump())
    except IntegrityError as exc:
        session.rollback()
        raise _admin_error(exc) from exc
    return SlaPolicyResponse.model_validate(item)


@router.patch("/sla-policies/{policy_id}", response_model=SlaPolicyResponse)
def update_sla_policy(
    request: SlaPolicyUpdateRequest,
    policy_id: str = Path(min_length=1, max_length=36),
    _admin: CurrentUser = Depends(require_admin),  # noqa: B008
    session: Session = Depends(get_db),  # noqa: B008
) -> SlaPolicyResponse:
    item = AdminConfigRepository(session).update_sla_policy(
        policy_id, request.model_dump(exclude_unset=True)
    )
    if item is None:
        raise AppError("SLA_POLICY_NOT_FOUND", "SLA 策略不存在", 404, {})
    return SlaPolicyResponse.model_validate(item)


@router.get("/service-catalog", response_model=list[ServiceCatalogResponse])
def list_service_catalog(
    _admin: CurrentUser = Depends(require_admin),  # noqa: B008
    session: Session = Depends(get_db),  # noqa: B008
) -> list[ServiceCatalogResponse]:
    return AdminConfigRepository(session).list_catalog()


@router.post(
    "/service-catalog",
    response_model=ServiceCatalogResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_service_catalog_item(
    request: ServiceCatalogCreateRequest,
    _admin: CurrentUser = Depends(require_admin),  # noqa: B008
    session: Session = Depends(get_db),  # noqa: B008
) -> ServiceCatalogResponse:
    try:
        repository = AdminConfigRepository(session)
        item = repository.create_catalog_item(request.model_dump())
    except IntegrityError as exc:
        session.rollback()
        raise _admin_error(exc) from exc
    return repository.catalog_response(item)


@router.patch("/service-catalog/{item_id}", response_model=ServiceCatalogResponse)
def update_service_catalog_item(
    request: ServiceCatalogUpdateRequest,
    item_id: str = Path(min_length=1, max_length=36),
    _admin: CurrentUser = Depends(require_admin),  # noqa: B008
    session: Session = Depends(get_db),  # noqa: B008
) -> ServiceCatalogResponse:
    repository = AdminConfigRepository(session)
    item = repository.update_catalog_item(item_id, request.model_dump(exclude_unset=True))
    if item is None:
        raise AppError("SERVICE_NOT_FOUND", "服务目录项不存在", 404, {})
    return repository.catalog_response(item)
