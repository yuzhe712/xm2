from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from intelliticket_backend.config import Settings
from intelliticket_backend.errors import AppError
from intelliticket_backend.models import AiRun, Ticket
from intelliticket_backend.repositories.tickets import TicketRepository
from intelliticket_backend.schemas.ai_runs import AiRunDecisionRequest, AiRunResponse


def _now() -> datetime:
    return datetime.now(UTC)


class AiRunRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, ticket: Ticket, settings: Settings, actor_id: str | None) -> AiRun:
        run = AiRun(
            id=f"RUN-{datetime.now(UTC):%Y%m%d}-{uuid4().hex[:8].upper()}",
            ticket_id=ticket.ticket_id,
            status="queued",
            stage="queued",
            progress=0,
            pipeline_version=settings.ai_pipeline_version,
            provider=settings.llm_provider,
            model=settings.llm_model,
            prompt_version=settings.ai_prompt_version,
            input_hash=hashlib.sha256(ticket.input_text.encode()).hexdigest(),
            retry_count=0,
            created_at=_now(),
            updated_at=_now(),
        )
        self.session.add(run)
        ticket.latest_run_id = run.id
        ticket.updated_at = _now().isoformat()
        self.session.flush()
        TicketRepository(self.session).add_event(
            ticket_id=ticket.ticket_id,
            actor_id=actor_id,
            event_type="ai_triage_queued",
            from_status=ticket.ticket_status,
            to_status=ticket.ticket_status,
            visibility="internal",
            payload={"run_id": run.id, "pipeline_version": run.pipeline_version},
        )
        return run

    def get(self, run_id: str) -> AiRun | None:
        return self.session.get(AiRun, run_id)

    def get_for_ticket(self, run_id: str) -> tuple[AiRun, Ticket] | None:
        row = self.session.execute(
            select(AiRun, Ticket)
            .join(Ticket, AiRun.ticket_id == Ticket.ticket_id)
            .where(AiRun.id == run_id)
        ).one_or_none()
        return row if row is not None else None

    def mark_dispatched(self, run_id: str, task_id: str) -> None:
        self.session.execute(
            update(AiRun)
            .where(AiRun.id == run_id, AiRun.status == "queued")
            .values(celery_task_id=task_id, updated_at=_now())
        )

    def mark_running(self, run_id: str, task_id: str | None = None) -> AiRun | None:
        now = _now()
        values = {
            "status": "running",
            "stage": "triage",
            "progress": 5,
            "started_at": now,
            "heartbeat_at": now,
            "updated_at": now,
            "error_code": None,
            "error_message": None,
        }
        if task_id:
            values["celery_task_id"] = task_id
        result = self.session.execute(
            update(AiRun)
            .where(AiRun.id == run_id, AiRun.status == "queued")
            .values(**values)
        )
        if result.rowcount != 1:
            return None
        self.session.flush()
        self.session.expire_all()
        return self.get(run_id)

    def mark_stage(self, run_id: str, stage: str, progress: int) -> None:
        now = _now()
        self.session.execute(
            update(AiRun)
            .where(AiRun.id == run_id, AiRun.status == "running")
            .values(stage=stage, progress=progress, heartbeat_at=now, updated_at=now)
        )

    def complete(
        self,
        run_id: str,
        *,
        result: dict,
        evidence: list[dict],
        confidence: float,
        prompt_tokens: int,
        completion_tokens: int,
        duration_ms: int,
    ) -> AiRun:
        run = self.get(run_id)
        if run is None:
            raise AppError("AI_RUN_NOT_FOUND", "AI 任务不存在", 404, {"run_id": run_id})
        now = _now()
        run.status = "completed"
        run.stage = "completed"
        run.progress = 100
        run.result_json = result
        run.evidence_json = evidence
        run.confidence = confidence
        run.prompt_tokens = prompt_tokens
        run.completion_tokens = completion_tokens
        run.duration_ms = duration_ms
        run.completed_at = now
        run.heartbeat_at = now
        run.updated_at = now
        ticket = self.session.get(Ticket, run.ticket_id)
        if ticket is not None:
            triage = result.get("triage", {}).get("classification", {})
            quality_gate = result.get("quality_gate", {})
            if triage:
                ticket.category = triage.get("category")
                ticket.priority = triage.get("priority") or ticket.priority
                ticket.assessed_priority = ticket.priority
                ticket.assessed_priority_reason = triage.get("priority_reason")
                ticket.affected_service = triage.get("affected_service")
            if quality_gate.get("recommended_team"):
                ticket.assigned_team = quality_gate["recommended_team"]
            previous = ticket.ticket_status
            if previous == "pending":
                ticket.ticket_status = "open"
                ticket.version += 1
            TicketRepository(self.session).add_event(
                ticket_id=ticket.ticket_id,
                actor_id=None,
                event_type="ai_triage_completed",
                from_status=previous,
                to_status=ticket.ticket_status,
                visibility="internal",
                payload={"run_id": run.id, "confidence": confidence},
            )
            ticket.updated_at = now.isoformat()
        self.session.flush()
        return run

    def fail(self, run_id: str, code: str, message: str, *, terminal: bool = True) -> None:
        run = self.get(run_id)
        if run is None:
            return
        now = _now()
        run.status = "failed" if terminal else "queued"
        run.stage = "failed" if terminal else "retrying"
        run.error_code = code
        run.error_message = message[:2000]
        run.completed_at = now if terminal else None
        run.heartbeat_at = now
        run.updated_at = now
        if not terminal:
            run.retry_count += 1
        ticket = self.session.get(Ticket, run.ticket_id)
        if ticket is not None:
            TicketRepository(self.session).add_event(
                ticket_id=ticket.ticket_id,
                actor_id=None,
                event_type="ai_triage_failed" if terminal else "ai_triage_retrying",
                from_status=ticket.ticket_status,
                to_status=ticket.ticket_status,
                visibility="internal",
                payload={"run_id": run.id, "error_code": code},
            )

    def recover_stale(self, stale_seconds: int, max_retries: int) -> list[str]:
        cutoff = _now() - timedelta(seconds=stale_seconds)
        runs = self.session.scalars(
            select(AiRun).where(
                AiRun.status == "running",
                AiRun.retry_count < max_retries,
                or_(
                    AiRun.heartbeat_at < cutoff,
                    AiRun.heartbeat_at.is_(None),
                ),
            )
        ).all()
        for run in runs:
            run.status = "queued"
            run.stage = "recovered"
            run.progress = 0
            run.retry_count += 1
            run.error_code = "AI_RUN_STALE_RECOVERED"
            run.error_message = "陈旧运行已重新入队"
            run.started_at = None
            run.completed_at = None
            run.heartbeat_at = _now()
            run.updated_at = _now()
        self.session.flush()
        return [run.id for run in runs]

    def decide(
        self,
        run_id: str,
        request: AiRunDecisionRequest,
        actor_id: str,
    ) -> AiRun:
        run = self.get(run_id)
        if run is None:
            raise AppError("AI_RUN_NOT_FOUND", "AI 任务不存在", 404, {"run_id": run_id})
        if run.status != "completed":
            raise AppError("AI_RUN_NOT_COMPLETED", "只能评审已完成的 AI 建议", 409, {})
        run.decision = request.decision
        run.decision_note = request.note.strip() if request.note else None
        run.modified_result_json = request.modified_result
        run.decided_by = actor_id
        run.decided_at = _now()
        run.updated_at = _now()
        ticket = self.session.get(Ticket, run.ticket_id)
        if ticket is not None:
            TicketRepository(self.session).add_event(
                ticket_id=ticket.ticket_id,
                actor_id=actor_id,
                event_type="ai_suggestion_decided",
                from_status=ticket.ticket_status,
                to_status=ticket.ticket_status,
                visibility="internal",
                payload={"run_id": run.id, "decision": request.decision},
            )
        self.session.flush()
        return run

    @staticmethod
    def to_response(run: AiRun) -> AiRunResponse:
        return AiRunResponse(
            id=run.id,
            ticket_id=run.ticket_id,
            status=run.status,
            celery_task_id=run.celery_task_id,
            stage=run.stage,
            progress=run.progress,
            pipeline_version=run.pipeline_version,
            provider=run.provider,
            model=run.model,
            prompt_version=run.prompt_version,
            result=run.result_json,
            evidence=run.evidence_json or [],
            confidence=run.confidence,
            error_code=run.error_code,
            error_message=run.error_message,
            prompt_tokens=run.prompt_tokens,
            completion_tokens=run.completion_tokens,
            retry_count=run.retry_count,
            duration_ms=run.duration_ms,
            decision=run.decision,
            decision_note=run.decision_note,
            modified_result=run.modified_result_json,
            decided_by=run.decided_by,
            decided_at=run.decided_at.isoformat() if run.decided_at else None,
            started_at=run.started_at.isoformat() if run.started_at else None,
            completed_at=run.completed_at.isoformat() if run.completed_at else None,
            heartbeat_at=run.heartbeat_at.isoformat() if run.heartbeat_at else None,
            created_at=run.created_at.isoformat(),
            updated_at=run.updated_at.isoformat(),
        )
