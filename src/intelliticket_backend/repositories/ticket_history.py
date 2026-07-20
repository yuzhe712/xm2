from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from intelliticket_backend.schemas.orchestration import (
    RouteDecision,
    SupervisorRunFailure,
    SupervisorRunResult,
)
from intelliticket_backend.schemas.ticket_history import (
    StoredAgentRun,
    StoredRunDetail,
    SupportReplyDraftResponse,
    SupportReplyDraftUpdateRequest,
    TicketHistoryDetailResponse,
    TicketHistoryListResponse,
    TicketHistorySummary,
    TicketLifecycleUpdateRequest,
)
from intelliticket_backend.schemas.tickets import (
    DeskId,
    Evidence,
    TicketProcessRequest,
    TicketProcessResponse,
)
from intelliticket_backend.services.agents.envelope import AgentTaskError, ReActStep

AGENT_TO_STEP = {
    "ticket_intake_agent": "ticket_intake",
    "context_retrieval_agent": "context_retrieval",
    "diagnosis_agent": "diagnosis",
    "routing_agent": "routing",
    "report_agent": "report",
    "support_intake_service": "support_intake",
    "support_kb_retrieval_service": "support_kb_retrieval",
    "support_kb_retrieval_agent": "support_kb_retrieval",
    "support_routing_service": "support_routing",
    "support_reply_suggestion_service": "support_reply_suggestion",
    "support_reply_agent": "support_reply_suggestion",
}

TICKETS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS tickets (
    ticket_id TEXT PRIMARY KEY,
    desk_id TEXT NOT NULL DEFAULT 'ops' CHECK (desk_id IN ('ops', 'support')),
    input_text TEXT NOT NULL,
    data_mode TEXT NOT NULL CHECK (data_mode IN ('mock', 'demo', 'real')),
    submitter TEXT DEFAULT NULL,
    summary TEXT,
    affected_service TEXT,
    priority TEXT,
    report_title TEXT,
    ticket_status TEXT NOT NULL DEFAULT 'pending' CHECK (
        ticket_status IN ('pending', 'open', 'in_progress', 'resolved', 'closed', 'cancelled')
    ),
    assigned_team TEXT,
    resolution_summary TEXT,
    closed_at TEXT,
    latest_run_id TEXT DEFAULT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""

RUNS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    ticket_id TEXT NOT NULL REFERENCES tickets(ticket_id) ON DELETE CASCADE,
    status TEXT NOT NULL CHECK (status IN ('completed', 'failed', 'cancelled')),
    data_mode TEXT NOT NULL CHECK (data_mode IN ('mock', 'demo', 'real')),
    route_mode TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT NOT NULL,
    response_json TEXT,
    error_json TEXT,
    agent_trace_json TEXT NOT NULL,
    supervisor_decisions_json TEXT NOT NULL
);
"""

DEPENDENT_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS agent_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    ticket_id TEXT NOT NULL REFERENCES tickets(ticket_id) ON DELETE CASCADE,
    sequence INTEGER NOT NULL,
    task_id TEXT NOT NULL,
    agent_name TEXT NOT NULL,
    step TEXT NOT NULL,
    status TEXT NOT NULL,
    route_decision_json TEXT NOT NULL,
    observations_json TEXT NOT NULL,
    react_steps_json TEXT NOT NULL DEFAULT '[]',
    evidence_ids_json TEXT NOT NULL,
    error_json TEXT,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    UNIQUE (run_id, task_id)
);

CREATE TABLE IF NOT EXISTS support_reply_drafts (
    draft_id TEXT PRIMARY KEY,
    ticket_id TEXT NOT NULL REFERENCES tickets(ticket_id) ON DELETE CASCADE,
    run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    reply_text TEXT NOT NULL,
    report_summary TEXT,
    evidence_ids_json TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('draft', 'approved', 'sent', 'discarded')),
    source TEXT NOT NULL DEFAULT 'human_edited_from_deterministic_suggestion',
    editor TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    approved_at TEXT,
    sent_at TEXT,
    UNIQUE(ticket_id)
);

CREATE TABLE IF NOT EXISTS evidence (
    run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    ticket_id TEXT NOT NULL REFERENCES tickets(ticket_id) ON DELETE CASCADE,
    evidence_id TEXT NOT NULL,
    source_type TEXT NOT NULL,
    source_id TEXT NOT NULL,
    source_name TEXT NOT NULL,
    service TEXT,
    metric_name TEXT,
    quality TEXT NOT NULL,
    data_mode TEXT NOT NULL CHECK (data_mode IN ('mock', 'demo', 'real')),
    observed_at TEXT,
    retrieved_at TEXT,
    summary TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    PRIMARY KEY (run_id, evidence_id)
);

CREATE INDEX IF NOT EXISTS idx_tickets_updated_at ON tickets(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_tickets_data_mode ON tickets(data_mode);
CREATE INDEX IF NOT EXISTS idx_tickets_desk_id ON tickets(desk_id);
CREATE INDEX IF NOT EXISTS idx_tickets_ticket_status ON tickets(ticket_status);
CREATE INDEX IF NOT EXISTS idx_tickets_assigned_team ON tickets(assigned_team);
CREATE INDEX IF NOT EXISTS idx_runs_ticket_id ON runs(ticket_id);
CREATE INDEX IF NOT EXISTS idx_support_reply_drafts_ticket_id ON support_reply_drafts(ticket_id);
CREATE INDEX IF NOT EXISTS idx_agent_runs_run_id ON agent_runs(run_id, sequence);
CREATE INDEX IF NOT EXISTS idx_evidence_run_id ON evidence(run_id);
"""

CASE_LIBRARY_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS case_library (
    ticket_id TEXT PRIMARY KEY REFERENCES tickets(ticket_id) ON DELETE CASCADE,
    input_text TEXT NOT NULL,
    symptoms_json TEXT NOT NULL DEFAULT '[]',
    data_mode TEXT NOT NULL DEFAULT 'mock' CHECK (data_mode IN ('mock', 'demo', 'real')),
    root_cause TEXT NOT NULL DEFAULT '',
    confirmed_root_cause TEXT NOT NULL DEFAULT '',
    resolution TEXT NOT NULL DEFAULT '',
    affected_service TEXT NOT NULL DEFAULT '',
    priority TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
"""


class TicketHistoryRepository:
    """SQLite-backed processed ticket history repository."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        if str(db_path) != ":memory:":
            db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize_schema()

    def save_completed_run(
        self,
        *,
        request: TicketProcessRequest,
        run_result: SupervisorRunResult,
        route_mode: str,
    ) -> None:
        response = run_result.response
        self._save_run(
            request=request,
            ticket_id=response.ticket_id,
            run_id=response.run_id,
            status="completed",
            data_mode=response.data_mode.value,
            route_mode=route_mode,
            started_at=run_result.started_at,
            completed_at=run_result.completed_at,
            response=response,
            error=None,
            agent_runs=run_result.agent_runs,
            route_decisions=run_result.route_decisions,
            evidence=response.evidence,
            desk_id=request.desk_id.value,
            ticket_status="in_progress",
            claimed_by=request.operator_id,
            assigned_team=response.routing.recommended_team,
            resolution_summary=None,
            closed_at=None,
            summary=response.classification.summary,
            affected_service=response.classification.affected_service,
            priority=response.classification.priority.value,
            report_title=response.report.title,
        )
        # Persist to case library AFTER ticket row exists (FK constraint)
        root_cause = ""
        if response.diagnosis.candidate_root_causes:
            root_cause = response.diagnosis.candidate_root_causes[0].cause
        self.save_case(
            ticket_id=response.ticket_id,
            input_text=request.text,
            symptoms=response.classification.symptoms,
            data_mode=response.data_mode.value,
            root_cause=root_cause,
            affected_service=response.classification.affected_service or "",
            priority=response.classification.priority.value,
        )

    def save_failed_run(
        self,
        *,
        request: TicketProcessRequest,
        run_failure: SupervisorRunFailure,
        route_mode: str,
    ) -> None:
        self._save_run(
            request=request,
            ticket_id=run_failure.ticket_id,
            run_id=run_failure.run_id,
            status=run_failure.status,
            data_mode=run_failure.data_mode.value,
            route_mode=route_mode,
            started_at=run_failure.started_at,
            completed_at=run_failure.completed_at,
            response=None,
            error=run_failure.error,
            agent_runs=run_failure.agent_runs,
            route_decisions=run_failure.route_decisions,
            evidence=run_failure.evidence,
            desk_id=request.desk_id.value,
            ticket_status="cancelled" if run_failure.status == "cancelled" else "open",
            claimed_by=None,
            assigned_team=None,
            resolution_summary=None,
            closed_at=None,
            summary=self._request_summary(request.text),
            affected_service=None,
            priority=None,
            report_title=None,
        )

    def list_tickets(
        self,
        *,
        limit: int,
        offset: int,
        desk_id: DeskId | None = None,
    ) -> TicketHistoryListResponse:
        with self._connect() as connection:
            if desk_id is None:
                total = connection.execute(
                    "SELECT COUNT(*) AS count FROM tickets"
                ).fetchone()["count"]
                rows = connection.execute(
                    """
                    SELECT t.ticket_id, t.desk_id, t.latest_run_id, t.created_at,
                           t.updated_at, t.data_mode, t.submitter,
                           t.assessed_priority, t.assessed_priority_reason,
                           t.sla_deadline, t.claimed_by, t.claimed_at,
                           COALESCE(r.status, 'pending') AS status,
                           t.ticket_status,
                           t.assigned_team, t.resolution_summary, t.closed_at,
                           t.summary, t.affected_service, t.priority, t.report_title
                    FROM tickets t
                    LEFT JOIN runs r ON r.run_id = t.latest_run_id
                    ORDER BY t.updated_at DESC, t.ticket_id DESC
                    LIMIT ? OFFSET ?
                    """,
                    (limit, offset),
                ).fetchall()
            else:
                total = connection.execute(
                    "SELECT COUNT(*) AS count FROM tickets WHERE desk_id = ?",
                    (desk_id.value,),
                ).fetchone()["count"]
                rows = connection.execute(
                    """
                    SELECT t.ticket_id, t.desk_id, t.latest_run_id, t.created_at,
                           t.updated_at, t.data_mode, t.submitter,
                           t.assessed_priority, t.assessed_priority_reason,
                           COALESCE(r.status, 'pending') AS status,
                           t.ticket_status,
                           t.assigned_team, t.resolution_summary, t.closed_at,
                           t.summary, t.affected_service, t.priority, t.report_title
                    FROM tickets t
                    LEFT JOIN runs r ON r.run_id = t.latest_run_id
                    WHERE t.desk_id = ?
                    ORDER BY t.updated_at DESC, t.ticket_id DESC
                    LIMIT ? OFFSET ?
                    """,
                    (desk_id.value, limit, offset),
                ).fetchall()
        return TicketHistoryListResponse(
            items=[TicketHistorySummary.model_validate(dict(row)) for row in rows],
            limit=limit,
            offset=offset,
            total=total,
        )

    def upsert_support_reply_draft(
        self,
        ticket_id: str,
        update: SupportReplyDraftUpdateRequest,
    ) -> TicketHistoryDetailResponse | None:
        with self._connect() as connection:
            ticket = connection.execute(
                "SELECT ticket_id, latest_run_id FROM tickets WHERE ticket_id = ?",
                (ticket_id,),
            ).fetchone()
            if ticket is None:
                return None
            run = connection.execute(
                "SELECT response_json FROM runs WHERE run_id = ?",
                (ticket["latest_run_id"],),
            ).fetchone()
            response_json = self._load(run["response_json"]) if run else None
            response = (
                TicketProcessResponse.model_validate(response_json) if response_json else None
            )
            if response is None or response.classification.category != "support_request":
                from intelliticket_backend.errors import AppError

                raise AppError(
                    "SUPPORT_DRAFT_NOT_ALLOWED",
                    "只有 support 工单可以保存内部支持回复草稿",
                    400,
                    {"ticket_id": ticket_id},
                )
            known_evidence_ids = {item.evidence_id for item in response.evidence}
            unknown = sorted(set(update.evidence_ids) - known_evidence_ids)
            if unknown:
                from intelliticket_backend.errors import AppError

                raise AppError(
                    "SUPPORT_DRAFT_EVIDENCE_UNKNOWN",
                    "回复草稿引用了未知证据",
                    400,
                    {"ticket_id": ticket_id, "unknown_evidence_ids": unknown},
                )
            now = self._now()
            existing = connection.execute(
                "SELECT * FROM support_reply_drafts WHERE ticket_id = ?",
                (ticket_id,),
            ).fetchone()
            created_at = existing["created_at"] if existing else now
            draft_id = existing["draft_id"] if existing else f"DRF-{uuid4().hex[:12].upper()}"
            approved_at = existing["approved_at"] if existing else None
            sent_at = existing["sent_at"] if existing else None
            if update.status in {"approved", "sent"} and approved_at is None:
                approved_at = now
            if update.status == "sent":
                sent_at = sent_at or now
            connection.execute(
                """
                INSERT INTO support_reply_drafts (
                    draft_id, ticket_id, run_id, reply_text, report_summary, evidence_ids_json,
                    status, source, editor, created_at, updated_at, approved_at, sent_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(ticket_id) DO UPDATE SET
                    run_id = excluded.run_id,
                    reply_text = excluded.reply_text,
                    report_summary = excluded.report_summary,
                    evidence_ids_json = excluded.evidence_ids_json,
                    status = excluded.status,
                    editor = excluded.editor,
                    updated_at = excluded.updated_at,
                    approved_at = excluded.approved_at,
                    sent_at = excluded.sent_at
                """,
                (
                    draft_id,
                    ticket_id,
                    ticket["latest_run_id"],
                    update.reply_text.strip(),
                    update.report_summary.strip() if update.report_summary else None,
                    self._dump(update.evidence_ids),
                    update.status,
                    "human_edited_from_deterministic_suggestion",
                    update.editor.strip() if update.editor else None,
                    created_at,
                    now,
                    approved_at,
                    sent_at,
                ),
            )
        return self.get_ticket(ticket_id)

    def update_ticket_lifecycle(
        self,
        ticket_id: str,
        update: TicketLifecycleUpdateRequest,
    ) -> TicketHistoryDetailResponse | None:
        with self._connect() as connection:
            current = connection.execute(
                "SELECT ticket_id FROM tickets WHERE ticket_id = ?",
                (ticket_id,),
            ).fetchone()
            if current is None:
                return None
            ticket_status = update.ticket_status
            closed_at = self._now() if ticket_status == "closed" else None
            assignments = ["updated_at = ?"]
            values: list[Any] = [self._now()]
            if ticket_status is not None:
                assignments.append("ticket_status = ?")
                values.append(ticket_status)
                assignments.append("closed_at = ?")
                values.append(closed_at)
            if update.resolution_summary is not None:
                assignments.append("resolution_summary = ?")
                values.append(update.resolution_summary.strip() or None)
            if update.root_cause is not None:
                assignments.append("root_cause = ?")
                values.append(update.root_cause.strip() or None)
            if update.fix_action is not None:
                assignments.append("fix_action = ?")
                values.append(update.fix_action.strip() or None)
            if update.verification is not None:
                assignments.append("verification = ?")
                values.append(update.verification.strip() or None)
            values.append(ticket_id)
            connection.execute(
                f"UPDATE tickets SET {', '.join(assignments)} WHERE ticket_id = ?",
                values,
            )
        return self.get_ticket(ticket_id)

    def get_ticket(self, ticket_id: str) -> TicketHistoryDetailResponse | None:
        with self._connect() as connection:
            ticket = connection.execute(
                "SELECT * FROM tickets WHERE ticket_id = ?",
                (ticket_id,),
            ).fetchone()
            if ticket is None:
                return None
            run = connection.execute(
                "SELECT * FROM runs WHERE run_id = ?",
                (ticket["latest_run_id"],),
            ).fetchone()
            if run is None:
                draft = connection.execute(
                    "SELECT * FROM support_reply_drafts WHERE ticket_id = ?",
                    (ticket_id,),
                ).fetchone()
                return TicketHistoryDetailResponse(
                    ticket_id=ticket["ticket_id"],
                    desk_id=ticket["desk_id"],
                    input_text=ticket["input_text"],
                    data_mode=ticket["data_mode"],
                    ticket_status=ticket["ticket_status"],
                    assigned_team=ticket["assigned_team"],
                    resolution_summary=ticket["resolution_summary"],
                    root_cause=(
                        ticket["root_cause"] if "root_cause" in ticket.keys() else None
                    ),
                    fix_action=(
                        ticket["fix_action"] if "fix_action" in ticket.keys() else None
                    ),
                    verification=(
                        ticket["verification"] if "verification" in ticket.keys() else None
                    ),
                    closed_at=ticket["closed_at"],
                    submitter=ticket["submitter"],
                    created_at=ticket["created_at"],
                    updated_at=ticket["updated_at"],
                    support_reply_draft=self._draft_from_row(draft) if draft else None,
                    latest_run=None,
                )
            agent_run_rows = connection.execute(
                """
                SELECT * FROM agent_runs
                WHERE run_id = ?
                ORDER BY sequence ASC
                """,
                (run["run_id"],),
            ).fetchall()
            evidence_rows = connection.execute(
                """
                SELECT payload_json FROM evidence
                WHERE run_id = ?
                ORDER BY evidence_id ASC
                """,
                (run["run_id"],),
            ).fetchall()
            draft = connection.execute(
                "SELECT * FROM support_reply_drafts WHERE ticket_id = ?",
                (ticket_id,),
            ).fetchone()

        response_json = self._load(run["response_json"])
        response = TicketProcessResponse.model_validate(response_json) if response_json else None
        error_json = self._load(run["error_json"])
        error = AgentTaskError.model_validate(error_json) if error_json else None
        supervisor_decisions = [
            RouteDecision.model_validate(item)
            for item in self._load(run["supervisor_decisions_json"])
        ]
        agent_runs = [self._agent_run_from_row(row) for row in agent_run_rows]
        evidence = [
            Evidence.model_validate(self._load(row["payload_json"])) for row in evidence_rows
        ]
        return TicketHistoryDetailResponse(
            ticket_id=ticket["ticket_id"],
            desk_id=ticket["desk_id"],
            input_text=ticket["input_text"],
            data_mode=ticket["data_mode"],
            ticket_status=ticket["ticket_status"],
            submitter=ticket["submitter"],
            assigned_team=ticket["assigned_team"],
            resolution_summary=ticket["resolution_summary"],
            root_cause=ticket["root_cause"] if "root_cause" in ticket.keys() else None,
            fix_action=ticket["fix_action"] if "fix_action" in ticket.keys() else None,
            verification=ticket["verification"] if "verification" in ticket.keys() else None,
            closed_at=ticket["closed_at"],
            created_at=ticket["created_at"],
            updated_at=ticket["updated_at"],
            support_reply_draft=self._draft_from_row(draft) if draft else None,
            latest_run=StoredRunDetail(
                run_id=run["run_id"],
                status=run["status"],
                data_mode=run["data_mode"],
                route_mode=run["route_mode"],
                started_at=run["started_at"],
                completed_at=run["completed_at"],
                response=response,
                error=error,
                agent_runs=agent_runs,
                supervisor_decisions=supervisor_decisions,
                evidence=evidence,
            ),
        )

    def _save_run(
        self,
        *,
        request: TicketProcessRequest,
        ticket_id: str,
        run_id: str,
        status: str,
        data_mode: str,
        route_mode: str,
        started_at: str,
        completed_at: str,
        response: TicketProcessResponse | None,
        error: AgentTaskError | None,
        agent_runs: list[Any],
        route_decisions: list[RouteDecision],
        evidence: list[Evidence],
        desk_id: str,
        ticket_status: str,
        claimed_by: str | None,
        assigned_team: str | None,
        resolution_summary: str | None,
        closed_at: str | None,
        summary: str,
        affected_service: str | None,
        priority: str | None,
        report_title: str | None,
    ) -> None:
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT created_at, submitter FROM tickets WHERE ticket_id = ?",
                (ticket_id,),
            ).fetchone()
            created_at = existing["created_at"] if existing else started_at
            existing_submitter = (
                existing["submitter"] if existing else request.submitter
            )
            submitter = request.submitter or existing_submitter
            sla = self._compute_sla(priority, completed_at) if response else None
            connection.execute(
                """
                INSERT INTO tickets (
                    ticket_id, desk_id, input_text, data_mode, submitter, summary,
                    affected_service, priority, report_title, ticket_status,
                    assigned_team, claimed_by, claimed_at, resolution_summary, closed_at,
                    latest_run_id, created_at, updated_at,
                    assessed_priority, assessed_priority_reason,
                    sla_deadline
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(ticket_id) DO UPDATE SET
                    desk_id = excluded.desk_id,
                    input_text = excluded.input_text,
                    data_mode = excluded.data_mode,
                    submitter = COALESCE(excluded.submitter, tickets.submitter),
                    summary = excluded.summary,
                    affected_service = excluded.affected_service,
                    priority = excluded.priority,
                    report_title = excluded.report_title,
                    ticket_status = excluded.ticket_status,
                    assigned_team = excluded.assigned_team,
                    claimed_by = COALESCE(excluded.claimed_by, tickets.claimed_by),
                    claimed_at = COALESCE(excluded.claimed_at, tickets.claimed_at),
                    resolution_summary = excluded.resolution_summary,
                    closed_at = excluded.closed_at,
                    latest_run_id = excluded.latest_run_id,
                    updated_at = excluded.updated_at,
                    assessed_priority = COALESCE(
                        excluded.assessed_priority, tickets.assessed_priority
                    ),
                    assessed_priority_reason = COALESCE(
                        excluded.assessed_priority_reason,
                        tickets.assessed_priority_reason
                    ),
                    sla_deadline = COALESCE(
                        excluded.sla_deadline, tickets.sla_deadline
                    )
                """,
                (
                    ticket_id,
                    desk_id,
                    request.text,
                    data_mode,
                    submitter,
                    summary,
                    affected_service,
                    priority,
                    report_title,
                    ticket_status,
                    assigned_team,
                    claimed_by,
                    completed_at if claimed_by else None,
                    resolution_summary,
                    closed_at,
                    run_id,
                    created_at,
                    completed_at,
                    priority,
                    (
                        f"由 {response.classification.category.value} Agent "
                        "基于工单内容和上下文自动判定"
                    )
                    if response
                    else None,
                    sla,
                ),
            )
            connection.execute(
                """
                INSERT INTO runs (
                    run_id, ticket_id, status, data_mode, route_mode, started_at,
                    completed_at, response_json, error_json, agent_trace_json,
                    supervisor_decisions_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    ticket_id,
                    status,
                    data_mode,
                    route_mode,
                    started_at,
                    completed_at,
                    self._dump(response.model_dump(mode="json")) if response else None,
                    self._dump(error.model_dump(mode="json")) if error else None,
                    self._dump(
                        [item.model_dump(mode="json") for item in response.agent_trace]
                        if response
                        else []
                    ),
                    self._dump([item.model_dump(mode="json") for item in route_decisions]),
                ),
            )
            for sequence, agent_run in enumerate(agent_runs, start=1):
                self._insert_agent_run(connection, run_id, ticket_id, sequence, agent_run)
            for item in evidence:
                self._insert_evidence(connection, run_id, ticket_id, item)

    def _initialize_schema(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA foreign_keys = OFF")
            connection.executescript(TICKETS_TABLE_SQL)
            self._migrate_tickets_table(connection)
            self._migrate_runs_table(connection)
            connection.executescript(DEPENDENT_SCHEMA_SQL)
            self._migrate_agent_runs_table(connection)
            connection.execute(CASE_LIBRARY_TABLE_SQL)
            self._migrate_case_library_table(connection)
            connection.execute("PRAGMA foreign_keys = ON")

    def _migrate_tickets_table(self, connection: sqlite3.Connection) -> None:
        columns = {
            column["name"]
            for column in connection.execute("PRAGMA table_info(tickets)").fetchall()
        }
        if "desk_id" not in columns:
            connection.execute(
                "ALTER TABLE tickets ADD COLUMN desk_id TEXT NOT NULL DEFAULT 'ops'"
            )
        if "ticket_status" not in columns:
            connection.execute(
                "ALTER TABLE tickets ADD COLUMN ticket_status TEXT NOT NULL DEFAULT 'open'"
            )
        if "assigned_team" not in columns:
            connection.execute("ALTER TABLE tickets ADD COLUMN assigned_team TEXT")
        if "resolution_summary" not in columns:
            connection.execute("ALTER TABLE tickets ADD COLUMN resolution_summary TEXT")
        if "closed_at" not in columns:
            connection.execute("ALTER TABLE tickets ADD COLUMN closed_at TEXT")
        if "submitter" not in columns:
            connection.execute("ALTER TABLE tickets ADD COLUMN submitter TEXT DEFAULT NULL")
        if "assessed_priority" not in columns:
            connection.execute(
                "ALTER TABLE tickets ADD COLUMN assessed_priority TEXT DEFAULT NULL"
            )
        if "assessed_priority_reason" not in columns:
            connection.execute(
                "ALTER TABLE tickets ADD COLUMN assessed_priority_reason TEXT DEFAULT NULL"
            )
        if "claimed_by" not in columns:
            connection.execute(
                "ALTER TABLE tickets ADD COLUMN claimed_by TEXT DEFAULT NULL"
            )
        if "claimed_at" not in columns:
            connection.execute(
                "ALTER TABLE tickets ADD COLUMN claimed_at TEXT DEFAULT NULL"
            )
        if "sla_deadline" not in columns:
            connection.execute(
                "ALTER TABLE tickets ADD COLUMN sla_deadline TEXT DEFAULT NULL"
            )
        if "root_cause" not in columns:
            connection.execute(
                "ALTER TABLE tickets ADD COLUMN root_cause TEXT DEFAULT NULL"
            )
        if "fix_action" not in columns:
            connection.execute(
                "ALTER TABLE tickets ADD COLUMN fix_action TEXT DEFAULT NULL"
            )
        if "verification" not in columns:
            connection.execute(
                "ALTER TABLE tickets ADD COLUMN verification TEXT DEFAULT NULL"
            )
        connection.execute("CREATE INDEX IF NOT EXISTS idx_tickets_desk_id ON tickets(desk_id)")

        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_tickets_submitter ON tickets(submitter)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_tickets_ticket_status ON tickets(ticket_status)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_tickets_assigned_team ON tickets(assigned_team)"
        )

    def _migrate_runs_table(self, connection: sqlite3.Connection) -> None:
        row = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'runs'"
        ).fetchone()
        table_sql = row["sql"] if row else ""
        columns = {
            column["name"]
            for column in connection.execute("PRAGMA table_info(runs)").fetchall()
        }
        if not row:
            connection.execute(RUNS_TABLE_SQL)
            return
        if (
            "error_json" in columns
            and "'failed'" in table_sql
            and "'cancelled'" in table_sql
            and "RESPONSE_JSON TEXT NOT NULL" not in table_sql.upper()
        ):
            return

        connection.execute("PRAGMA legacy_alter_table = ON")
        connection.execute("ALTER TABLE runs RENAME TO runs_old")
        connection.execute(RUNS_TABLE_SQL)
        connection.execute(
            """
            INSERT INTO runs (
                run_id, ticket_id, status, data_mode, route_mode, started_at,
                completed_at, response_json, error_json, agent_trace_json,
                supervisor_decisions_json
            )
            SELECT run_id, ticket_id, status, data_mode, route_mode, started_at,
                   completed_at, response_json, NULL, agent_trace_json,
                   supervisor_decisions_json
            FROM runs_old
            """
        )
        connection.execute("DROP TABLE runs_old")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_runs_ticket_id ON runs(ticket_id)")

    def _migrate_agent_runs_table(self, connection: sqlite3.Connection) -> None:
        columns = {
            column["name"]
            for column in connection.execute(
                "PRAGMA table_info(agent_runs)"
            ).fetchall()
        }
        if "react_steps_json" not in columns:
            connection.execute(
                "ALTER TABLE agent_runs ADD COLUMN react_steps_json"
                " TEXT NOT NULL DEFAULT '[]'"
            )

    def _migrate_case_library_table(self, connection: sqlite3.Connection) -> None:
        columns = {
            column["name"]
            for column in connection.execute("PRAGMA table_info(case_library)").fetchall()
        }
        if "data_mode" not in columns:
            connection.execute(
                "ALTER TABLE case_library ADD COLUMN data_mode TEXT NOT NULL DEFAULT 'mock'"
            )
        if "confirmed_root_cause" not in columns:
            connection.execute(
                "ALTER TABLE case_library ADD COLUMN confirmed_root_cause TEXT NOT NULL DEFAULT ''"
            )
        if "resolution" not in columns:
            connection.execute(
                "ALTER TABLE case_library ADD COLUMN resolution TEXT NOT NULL DEFAULT ''"
            )

    def save_case(
        self,
        ticket_id: str,
        input_text: str,
        symptoms: list[str],
        data_mode: str,
        root_cause: str,
        affected_service: str,
        priority: str,
    ) -> None:
        """将已完成的工单写入案例库。"""
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO case_library (
                    ticket_id, input_text, symptoms_json, data_mode, root_cause,
                    affected_service, priority, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(ticket_id) DO UPDATE SET
                    input_text = excluded.input_text,
                    symptoms_json = excluded.symptoms_json,
                    data_mode = excluded.data_mode,
                    root_cause = excluded.root_cause,
                    affected_service = excluded.affected_service,
                    priority = excluded.priority
                """,
                (
                    ticket_id,
                    input_text,
                    self._dump(symptoms),
                    data_mode,
                    root_cause,
                    affected_service,
                    priority,
                    self._now(),
                ),
            )

    def confirm_case(self, ticket_id: str, confirmed_root_cause: str, resolution: str = "") -> None:
        """人工确认案例根因。"""
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE case_library SET
                    confirmed_root_cause = ?,
                    resolution = ?
                WHERE ticket_id = ?
                """,
                (confirmed_root_cause, resolution, ticket_id),
            )

    def load_all_cases(self, data_mode: str | None = None) -> list[dict[str, Any]]:
        """加载案例记录；指定 data_mode 时只返回同模式案例。"""
        with self._connect() as connection:
            if data_mode is None:
                rows = connection.execute(
                    "SELECT * FROM case_library ORDER BY created_at DESC"
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT * FROM case_library WHERE data_mode = ? ORDER BY created_at DESC",
                    (data_mode,),
                ).fetchall()
        return [dict(row) for row in rows]

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _insert_agent_run(
        self,
        connection: sqlite3.Connection,
        run_id: str,
        ticket_id: str,
        sequence: int,
        agent_run: Any,
    ) -> None:
        connection.execute(
            """
            INSERT INTO agent_runs (
                run_id, ticket_id, sequence, task_id, agent_name, step, status,
                route_decision_json, observations_json, react_steps_json,
                evidence_ids_json, error_json,
                started_at, completed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                ticket_id,
                sequence,
                agent_run.task_id,
                agent_run.agent_name,
                AGENT_TO_STEP.get(agent_run.agent_name, agent_run.agent_name),
                agent_run.status,
                self._dump(
                    agent_run.route_decision.model_dump(mode="json")
                    if agent_run.route_decision
                    else None
                ),
                self._dump(agent_run.observations),
                self._dump(
                    [s.model_dump(mode="json") for s in agent_run.react_steps]
                    if agent_run.react_steps else []
                ),
                self._dump(agent_run.evidence_ids),
                self._dump(agent_run.error.model_dump(mode="json") if agent_run.error else None),
                agent_run.started_at,
                agent_run.completed_at,
            ),
        )

    def _insert_evidence(
        self,
        connection: sqlite3.Connection,
        run_id: str,
        ticket_id: str,
        item: Evidence,
    ) -> None:
        connection.execute(
            """
            INSERT INTO evidence (
                run_id, ticket_id, evidence_id, source_type, source_id, source_name,
                service, metric_name, quality, data_mode, observed_at, retrieved_at,
                summary, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                ticket_id,
                item.evidence_id,
                item.source_type,
                item.source_id,
                item.source_name,
                item.service,
                item.metric_name,
                item.quality,
                item.data_mode.value,
                item.observed_at,
                item.retrieved_at,
                item.summary,
                self._dump(item.model_dump(mode="json")),
            ),
        )

    def _draft_from_row(self, row: sqlite3.Row) -> SupportReplyDraftResponse:
        return SupportReplyDraftResponse(
            draft_id=row["draft_id"],
            ticket_id=row["ticket_id"],
            run_id=row["run_id"],
            source=row["source"],
            reply_text=row["reply_text"],
            report_summary=row["report_summary"],
            evidence_ids=self._load(row["evidence_ids_json"]),
            status=row["status"],
            editor=row["editor"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            approved_at=row["approved_at"],
            sent_at=row["sent_at"],
        )

    def _agent_run_from_row(self, row: sqlite3.Row) -> StoredAgentRun:
        route_decision = self._load(row["route_decision_json"])
        error = self._load(row["error_json"])
        react_steps_raw = self._load(
            row["react_steps_json"]
            if "react_steps_json" in row.keys() else "[]"
        ) or []
        react_steps = [ReActStep.model_validate(s) for s in react_steps_raw]
        return StoredAgentRun(
            sequence=row["sequence"],
            task_id=row["task_id"],
            agent_name=row["agent_name"],
            step=row["step"],
            status=row["status"],
            route_decision=(
                RouteDecision.model_validate(route_decision) if route_decision is not None else None
            ),
            observations=self._load(row["observations_json"]),
            react_steps=react_steps,
            evidence_ids=self._load(row["evidence_ids_json"]),
            error=AgentTaskError.model_validate(error) if error else None,
            started_at=row["started_at"],
            completed_at=row["completed_at"],
        )

    def save_pending_ticket(
        self,
        *,
        ticket_id: str,
        text: str,
        data_mode: str,
        desk_id: str,
        submitter: str,
        assessed_priority: str | None = None,
        assessed_priority_reason: str | None = None,
    ) -> dict[str, Any]:
        now = self._now()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO tickets (
                    ticket_id, desk_id, input_text, data_mode, submitter, ticket_status,
                    assessed_priority, assessed_priority_reason,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?)
                """,
                (
                    ticket_id, desk_id, text, data_mode, submitter,
                    assessed_priority, assessed_priority_reason,
                    now, now,
                ),
            )
        return {
            "ticket_id": ticket_id,
            "status": "pending",
            "created_at": now,
            "text": text,
            "desk_id": desk_id,
            "submitter": submitter,
            "assessed_priority": assessed_priority,
            "assessed_priority_reason": assessed_priority_reason,
        }

    def list_by_submitter(
        self,
        submitter: str,
        *,
        limit: int = 50,
        offset: int = 0,
        desk_id: str | None = None,
    ) -> TicketHistoryListResponse:
        with self._connect() as connection:
            if desk_id:
                total = connection.execute(
                    "SELECT COUNT(*) AS count FROM tickets WHERE submitter = ? AND desk_id = ?",
                    (submitter, desk_id),
                ).fetchone()["count"]
                rows = connection.execute(
                    """
                    SELECT t.ticket_id, t.desk_id, t.latest_run_id, t.created_at,
                           t.updated_at, t.data_mode, t.submitter,
                           t.assessed_priority, t.assessed_priority_reason,
                           t.sla_deadline, t.claimed_by, t.claimed_at,
                           t.ticket_status,
                           t.assigned_team, t.resolution_summary, t.closed_at,
                           t.summary, t.affected_service, t.priority, t.report_title
                    FROM tickets t
                    WHERE t.submitter = ? AND t.desk_id = ?
                    ORDER BY t.updated_at DESC, t.ticket_id DESC
                    LIMIT ? OFFSET ?
                    """,
                    (submitter, desk_id, limit, offset),
                ).fetchall()
            else:
                total = connection.execute(
                    "SELECT COUNT(*) AS count FROM tickets WHERE submitter = ?",
                    (submitter,),
                ).fetchone()["count"]
                rows = connection.execute(
                    """
                    SELECT t.ticket_id, t.desk_id, t.latest_run_id, t.created_at,
                           t.updated_at, t.data_mode, t.submitter,
                           t.assessed_priority, t.assessed_priority_reason,
                           t.sla_deadline, t.claimed_by, t.claimed_at,
                           t.ticket_status,
                           t.assigned_team, t.resolution_summary, t.closed_at,
                           t.summary, t.affected_service, t.priority, t.report_title
                    FROM tickets t
                    WHERE t.submitter = ?
                    ORDER BY t.updated_at DESC, t.ticket_id DESC
                    LIMIT ? OFFSET ?
                    """,
                    (submitter, limit, offset),
                ).fetchall()
        items = []
        for row in rows:
            d = dict(row)
            if d["latest_run_id"] is None:
                d["status"] = "pending"
            else:
                run = connection.execute(
                    "SELECT status FROM runs WHERE run_id = ?",
                    (d["latest_run_id"],),
                ).fetchone()
                d["status"] = run["status"] if run else "unknown"
            items.append(TicketHistorySummary.model_validate(d))
        return TicketHistoryListResponse(items=items, limit=limit, offset=offset, total=total)

    def list_pending(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> TicketHistoryListResponse:
        with self._connect() as connection:
            total = connection.execute(
                "SELECT COUNT(*) AS count FROM tickets WHERE ticket_status = 'pending'"
            ).fetchone()["count"]
            rows = connection.execute(
                """
                SELECT t.ticket_id, t.desk_id, t.latest_run_id, t.created_at,
                       t.updated_at, t.data_mode, 'pending' AS status,
                       t.ticket_status, t.submitter,
                       t.assigned_team, t.resolution_summary, t.closed_at,
                       t.summary, t.affected_service, t.priority, t.report_title
                FROM tickets t
                WHERE t.ticket_status = 'pending'
                ORDER BY t.created_at ASC
                LIMIT ? OFFSET ?
                """,
                (limit, offset),
            ).fetchall()
        items = [TicketHistorySummary.model_validate(dict(row)) for row in rows]
        return TicketHistoryListResponse(items=items, limit=limit, offset=offset, total=total)

    @staticmethod
    def _compute_sla(priority: str | None, base_time: str) -> str | None:
        from datetime import timedelta

        hours = {"P1": 4, "P2": 8, "P3": 48, "P4": 168}.get(priority or "", 48)
        dt = datetime.fromisoformat(base_time)
        return (dt + timedelta(hours=hours)).isoformat()

    def _now(self) -> str:
        return datetime.now(UTC).isoformat()

    def _request_summary(self, text: str) -> str:
        compact = " ".join(text.split())
        if len(compact) <= 120:
            return compact
        return f"{compact[:117]}..."

    def _dump(self, value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))

    def _load(self, value: str | None) -> Any:
        if value is None:
            return None
        return json.loads(value)
