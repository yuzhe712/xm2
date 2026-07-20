from __future__ import annotations

import sqlite3
from threading import Event

import pytest

from intelliticket_backend.repositories.ticket_history import TicketHistoryRepository
from intelliticket_backend.schemas.tickets import DataMode, DeskId, TicketProcessRequest
from intelliticket_backend.services.orchestrator import (
    OrchestrationRunError,
    SupervisorOrchestrator,
)

SAMPLE_TEXT = "线上支付服务出现超时告警，订单量从正常1000/min降到300/min"


def make_run_result():
    return SupervisorOrchestrator(route_mode="deterministic").run_with_audit(
        TicketProcessRequest(text=SAMPLE_TEXT, data_mode=DataMode.MOCK),
        ticket_id="TCK-20260715-ABCDEF12",
        run_id="RUN-20260715-1234ABCD",
    )


def test_repository_creates_required_tables(tmp_path) -> None:
    db_path = tmp_path / "history.sqlite3"
    TicketHistoryRepository(db_path)

    with sqlite3.connect(db_path) as connection:
        rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()

    table_names = {row[0] for row in rows}
    assert {"tickets", "runs", "agent_runs", "evidence"} <= table_names


def test_save_completed_run_can_list_and_load_after_reopen(tmp_path) -> None:
    db_path = tmp_path / "history.sqlite3"
    repository = TicketHistoryRepository(db_path)
    request = TicketProcessRequest(text=SAMPLE_TEXT, data_mode=DataMode.MOCK)
    run_result = make_run_result()

    repository.save_completed_run(
        request=request,
        run_result=run_result,
        route_mode="deterministic",
    )

    reopened = TicketHistoryRepository(db_path)
    listing = reopened.list_tickets(limit=20, offset=0)
    detail = reopened.get_ticket("TCK-20260715-ABCDEF12")

    assert listing.total == 1
    assert listing.items[0].ticket_id == "TCK-20260715-ABCDEF12"
    assert listing.items[0].desk_id == DeskId.OPS
    assert listing.items[0].data_mode == DataMode.MOCK
    assert listing.items[0].status == "completed"
    assert detail is not None
    assert detail.desk_id == DeskId.OPS
    assert detail.input_text == SAMPLE_TEXT
    assert detail.latest_run.response.ticket_id == "TCK-20260715-ABCDEF12"
    assert detail.latest_run.response.data_mode == DataMode.MOCK
    assert len(detail.latest_run.response.evidence) == len(run_result.response.evidence)
    assert len(detail.latest_run.evidence) == len(run_result.response.evidence)
    assert detail.latest_run.evidence[0].data_mode == DataMode.MOCK
    assert len(detail.latest_run.agent_runs) == 6
    assert len(detail.latest_run.supervisor_decisions) == 7
    assert detail.latest_run.supervisor_decisions[-1].next_agent == "finish"


def test_list_tickets_filters_by_desk_id(tmp_path) -> None:
    db_path = tmp_path / "history.sqlite3"
    repository = TicketHistoryRepository(db_path)
    for suffix, desk_id in [("ABCDEF12", DeskId.OPS), ("ABCDEF13", DeskId.SUPPORT)]:
        request = TicketProcessRequest(text=SAMPLE_TEXT, data_mode=DataMode.MOCK, desk_id=desk_id)
        run_result = SupervisorOrchestrator(route_mode="deterministic").run_with_audit(
            request,
            ticket_id=f"TCK-20260715-{suffix}",
            run_id=f"RUN-20260715-{suffix}",
        )
        repository.save_completed_run(
            request=request,
            run_result=run_result,
            route_mode="deterministic",
        )

    ops_listing = repository.list_tickets(limit=20, offset=0, desk_id=DeskId.OPS)
    support_listing = repository.list_tickets(limit=20, offset=0, desk_id=DeskId.SUPPORT)
    all_listing = repository.list_tickets(limit=20, offset=0)

    assert ops_listing.total == 1
    assert ops_listing.items[0].desk_id == DeskId.OPS
    assert support_listing.total == 1
    assert support_listing.items[0].desk_id == DeskId.SUPPORT
    assert all_listing.total == 2


def test_list_tickets_paginates_real_rows(tmp_path) -> None:
    db_path = tmp_path / "history.sqlite3"
    repository = TicketHistoryRepository(db_path)
    request = TicketProcessRequest(text=SAMPLE_TEXT, data_mode=DataMode.MOCK)
    for suffix in ["ABCDEF12", "ABCDEF13"]:
        run_result = SupervisorOrchestrator(route_mode="deterministic").run_with_audit(
            request,
            ticket_id=f"TCK-20260715-{suffix}",
            run_id=f"RUN-20260715-{suffix}",
        )
        repository.save_completed_run(
            request=request,
            run_result=run_result,
            route_mode="deterministic",
        )

    listing = repository.list_tickets(limit=1, offset=1)

    assert listing.total == 2
    assert len(listing.items) == 1


def test_save_failed_run_can_list_and_load_without_response(tmp_path) -> None:
    db_path = tmp_path / "history.sqlite3"
    repository = TicketHistoryRepository(db_path)
    request = TicketProcessRequest(text=SAMPLE_TEXT, data_mode=DataMode.MOCK)
    orchestrator = SupervisorOrchestrator(
        route_mode="deterministic",
        max_steps=1,
    )

    with pytest.raises(OrchestrationRunError) as exc_info:
        orchestrator.run_with_audit(
            request,
            ticket_id="TCK-20260715-ABCDEF12",
            run_id="RUN-20260715-1234ABCD",
        )

    repository.save_failed_run(
        request=request,
        run_failure=exc_info.value.run_failure,
        route_mode="deterministic",
    )

    reopened = TicketHistoryRepository(db_path)
    listing = reopened.list_tickets(limit=20, offset=0)
    detail = reopened.get_ticket("TCK-20260715-ABCDEF12")

    assert listing.total == 1
    assert listing.items[0].status == "failed"
    assert detail is not None
    assert detail.latest_run.status == "failed"
    assert detail.latest_run.response is None
    assert detail.latest_run.error is not None
    assert detail.latest_run.error.code == "ORCHESTRATOR_STEP_LIMIT_EXCEEDED"
    assert detail.latest_run.agent_runs
    assert detail.latest_run.supervisor_decisions
    assert detail.latest_run.evidence


def test_save_cancelled_run_can_list_and_load_without_response(tmp_path) -> None:
    db_path = tmp_path / "history.sqlite3"
    repository = TicketHistoryRepository(db_path)
    request = TicketProcessRequest(text=SAMPLE_TEXT, data_mode=DataMode.MOCK)
    cancel_event = Event()
    cancel_event.set()

    with pytest.raises(OrchestrationRunError) as exc_info:
        SupervisorOrchestrator(route_mode="deterministic").run_with_audit(
            request,
            ticket_id="TCK-20260715-ABCDEF12",
            run_id="RUN-20260715-1234ABCD",
            cancel_event=cancel_event,
        )

    repository.save_failed_run(
        request=request,
        run_failure=exc_info.value.run_failure,
        route_mode="deterministic",
    )

    detail = TicketHistoryRepository(db_path).get_ticket("TCK-20260715-ABCDEF12")

    assert detail is not None
    assert detail.latest_run.status == "cancelled"
    assert detail.latest_run.response is None
    assert detail.latest_run.error is not None
    assert detail.latest_run.error.code == "PROCESSING_CANCELLED"


def test_case_library_filters_by_data_mode(tmp_path) -> None:
    db_path = tmp_path / "history.sqlite3"
    repository = TicketHistoryRepository(db_path)
    repository.save_pending_ticket(
        ticket_id="TCK-20260715-ABCDEF12",
        text="mock 支付服务超时",
        data_mode=DataMode.MOCK.value,
        desk_id=DeskId.OPS.value,
        submitter="operator",
    )
    repository.save_pending_ticket(
        ticket_id="TCK-20260715-ABCDEF13",
        text="real DNS 解析失败",
        data_mode=DataMode.REAL.value,
        desk_id=DeskId.OPS.value,
        submitter="operator",
    )
    repository.save_case(
        ticket_id="TCK-20260715-ABCDEF12",
        input_text="mock 支付服务超时",
        symptoms=["timeout"],
        data_mode=DataMode.MOCK.value,
        root_cause="mock root cause",
        affected_service="payment-service",
        priority="P1",
    )
    repository.save_case(
        ticket_id="TCK-20260715-ABCDEF13",
        input_text="real DNS 解析失败",
        symptoms=["dns"],
        data_mode=DataMode.REAL.value,
        root_cause="real root cause",
        affected_service="dns-service",
        priority="P2",
    )

    mock_cases = repository.load_all_cases(DataMode.MOCK.value)
    real_cases = repository.load_all_cases(DataMode.REAL.value)

    assert [item["ticket_id"] for item in mock_cases] == ["TCK-20260715-ABCDEF12"]
    assert [item["ticket_id"] for item in real_cases] == ["TCK-20260715-ABCDEF13"]
    assert real_cases[0]["data_mode"] == DataMode.REAL.value


def test_repository_migrates_case_library_data_mode_as_mock(tmp_path) -> None:
    db_path = tmp_path / "history.sqlite3"
    with sqlite3.connect(db_path) as connection:
        connection.executescript(
            """
            CREATE TABLE tickets (
                ticket_id TEXT PRIMARY KEY,
                input_text TEXT NOT NULL,
                data_mode TEXT NOT NULL CHECK (data_mode IN ('mock', 'demo', 'real')),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE case_library (
                ticket_id TEXT PRIMARY KEY REFERENCES tickets(ticket_id) ON DELETE CASCADE,
                input_text TEXT NOT NULL,
                symptoms_json TEXT NOT NULL DEFAULT '[]',
                root_cause TEXT NOT NULL DEFAULT '',
                affected_service TEXT NOT NULL DEFAULT '',
                priority TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            );
            INSERT INTO tickets (ticket_id, input_text, data_mode, created_at, updated_at)
            VALUES ('TCK-20260715-ABCDEF12', '旧 mock 案例', 'mock', 'now', 'now');
            INSERT INTO case_library (
                ticket_id, input_text, symptoms_json, root_cause,
                affected_service, priority, created_at
            ) VALUES (
                'TCK-20260715-ABCDEF12', '旧 mock 案例', '[]',
                'legacy cause', 'payment-service', 'P1', 'now'
            );
            """
        )

    repository = TicketHistoryRepository(db_path)
    cases = repository.load_all_cases(DataMode.MOCK.value)

    assert cases[0]["ticket_id"] == "TCK-20260715-ABCDEF12"
    assert cases[0]["data_mode"] == DataMode.MOCK.value


def test_repository_migrates_completed_only_runs_table(tmp_path) -> None:
    db_path = tmp_path / "history.sqlite3"
    with sqlite3.connect(db_path) as connection:
        connection.executescript(
            """
            CREATE TABLE tickets (
                ticket_id TEXT PRIMARY KEY,
                input_text TEXT NOT NULL,
                data_mode TEXT NOT NULL CHECK (data_mode IN ('mock', 'demo', 'real')),
                summary TEXT,
                affected_service TEXT,
                priority TEXT,
                report_title TEXT,
                latest_run_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE runs (
                run_id TEXT PRIMARY KEY,
                ticket_id TEXT NOT NULL REFERENCES tickets(ticket_id) ON DELETE CASCADE,
                status TEXT NOT NULL CHECK (status IN ('completed')),
                data_mode TEXT NOT NULL CHECK (data_mode IN ('mock', 'demo', 'real')),
                route_mode TEXT NOT NULL,
                started_at TEXT NOT NULL,
                completed_at TEXT NOT NULL,
                response_json TEXT NOT NULL,
                agent_trace_json TEXT NOT NULL,
                supervisor_decisions_json TEXT NOT NULL
            );
            """
        )

    repository = TicketHistoryRepository(db_path)
    request = TicketProcessRequest(text=SAMPLE_TEXT, data_mode=DataMode.MOCK)
    cancel_event = Event()
    cancel_event.set()
    with pytest.raises(OrchestrationRunError) as exc_info:
        SupervisorOrchestrator(route_mode="deterministic").run_with_audit(
            request,
            ticket_id="TCK-20260715-ABCDEF12",
            run_id="RUN-20260715-1234ABCD",
            cancel_event=cancel_event,
        )

    repository.save_failed_run(
        request=request,
        run_failure=exc_info.value.run_failure,
        route_mode="deterministic",
    )

    listing = repository.list_tickets(limit=20, offset=0)
    assert listing.total == 1
    assert listing.items[0].status == "cancelled"
