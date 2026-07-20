from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Path, Query

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
    data_mode: Annotated[DataMode, Query()] = DataMode.MOCK,
) -> KnowledgeResponse:
    """查询指定服务台的知识库，默认返回本地 mock 知识。"""
    return ServiceDeskService().get_knowledge(desk_id, data_mode=data_mode)
