from __future__ import annotations

import pytest

from intelliticket_backend.errors import AppError
from intelliticket_backend.repositories.mock_ops_data import MockOpsDataRepository
from intelliticket_backend.schemas.tickets import DataMode, DeskId
from intelliticket_backend.services.service_desk import ServiceDeskService


def test_service_desk_catalog_is_scoped_by_desk() -> None:
    service = ServiceDeskService()

    ops = service.get_catalog(DeskId.OPS)
    support = service.get_catalog(DeskId.SUPPORT)

    assert ops.data_mode == DataMode.MOCK
    assert support.data_mode == DataMode.MOCK
    assert ops.items
    assert support.items
    assert {item.desk_scope for item in ops.items} == {DeskId.OPS}
    assert {item.desk_scope for item in support.items} == {DeskId.SUPPORT}
    assert {item.data_mode for item in ops.items} == {DataMode.MOCK}


def test_service_desk_knowledge_is_scoped_by_desk() -> None:
    service = ServiceDeskService()

    ops = service.get_knowledge(DeskId.OPS, data_mode=DataMode.MOCK)
    support = service.get_knowledge(DeskId.SUPPORT, data_mode=DataMode.MOCK)

    assert ops.items
    assert support.items
    assert {item.desk_scope for item in ops.items} == {DeskId.OPS}
    assert {item.desk_scope for item in support.items} == {DeskId.SUPPORT}
    assert ops.items[0].evidence_id
    assert support.items[0].source_name == "mock support knowledge base"


class EmptyRepository(MockOpsDataRepository):
    def get_catalog_items(self, desk_id: DeskId) -> list[dict]:
        return []

    def get_knowledge_articles(self, desk_id: DeskId) -> list[dict]:
        return []


def test_service_desk_empty_catalog_fails_closed() -> None:
    service = ServiceDeskService(repository=EmptyRepository())

    with pytest.raises(AppError) as exc_info:
        service.get_catalog(DeskId.OPS)

    assert exc_info.value.code == "DESK_CATALOG_EMPTY"


def test_service_desk_empty_knowledge_fails_closed() -> None:
    service = ServiceDeskService(repository=EmptyRepository())

    with pytest.raises(AppError) as exc_info:
        service.get_knowledge(DeskId.SUPPORT, data_mode=DataMode.MOCK)

    assert exc_info.value.code == "DESK_KNOWLEDGE_EMPTY"
