from __future__ import annotations

from intelliticket_backend.repositories.mock_ops_data import MockOpsDataRepository

REQUIRED_FIELDS = {
    "evidence_id",
    "source_type",
    "source_id",
    "source_name",
    "quality",
    "data_mode",
    "summary",
}


def test_mock_data_loads_and_is_explicitly_mock() -> None:
    repository = MockOpsDataRepository()

    all_data = repository.load_all()

    assert set(all_data) == {
        "services",
        "metrics",
        "deployments",
        "incidents",
        "sops",
        "catalog_items",
        "support_kb",
    }
    for records in all_data.values():
        assert records
        for record in records:
            assert record["data_mode"] == "mock"
            assert REQUIRED_FIELDS.issubset(record)
            assert record.get("observed_at") or record.get("retrieved_at")
    for key in ["catalog_items", "support_kb"]:
        scopes = {record["desk_scope"] for record in all_data[key]}
        assert {"ops", "support"} <= scopes


def test_resolves_payment_service_from_chinese_alias() -> None:
    repository = MockOpsDataRepository()

    service = repository.resolve_service("线上支付服务出现超时告警")

    assert service is not None
    assert service["name"] == "payment-service"
    assert service["owner_team"] == "支付系统运维组"
