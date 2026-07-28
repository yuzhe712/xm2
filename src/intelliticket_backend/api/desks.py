from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Path

from intelliticket_backend.config import get_settings
from intelliticket_backend.schemas.service_desk import CatalogResponse, KnowledgeResponse
from intelliticket_backend.schemas.tickets import DataMode, DeskId
from intelliticket_backend.services.service_desk import ServiceDeskService

router = APIRouter(prefix="/api/v1/desks", tags=["desks"])


@router.get("/{desk_id}/catalog", response_model=CatalogResponse)
def get_desk_catalog(desk_id: Annotated[DeskId, Path()]) -> CatalogResponse:
    """查询指定服务台的本地 mock 服务目录。"""
    return ServiceDeskService().get_catalog(desk_id)


@router.get("/{desk_id}/knowledge", response_model=KnowledgeResponse)
def get_desk_knowledge(
    desk_id: Annotated[DeskId, Path()],
) -> KnowledgeResponse:
    """按后端部署模式查询指定服务台的知识库。"""
    return ServiceDeskService().get_knowledge(
        desk_id, data_mode=DataMode(get_settings().data_mode)
    )
