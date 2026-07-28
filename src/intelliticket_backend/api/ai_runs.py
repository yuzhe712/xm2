from __future__ import annotations

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, Path, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from intelliticket_backend.config import get_settings
from intelliticket_backend.db import get_db, session_scope
from intelliticket_backend.errors import AppError
from intelliticket_backend.repositories.ai_runs import AiRunRepository
from intelliticket_backend.repositories.tickets import TicketRepository
from intelliticket_backend.schemas.ai_runs import (
    AiRunDecisionRequest,
    AiRunResponse,
    AiRunStatusEvent,
    StaleRecoveryResponse,
)
from intelliticket_backend.schemas.ticket_history import RUN_ID_PATTERN, TICKET_ID_PATTERN
from intelliticket_backend.schemas.users import CurrentUser
from intelliticket_backend.services.auth import (
    current_user_from_token,
    require_auth,
    require_operator,
)
from intelliticket_backend.services.permissions import ensure_ticket_visible
from intelliticket_backend.services.worker_tasks import dispatch_ai_run

router = APIRouter(prefix="/api/v1", tags=["ai-runs"])
RunId = Annotated[str, Path(pattern=RUN_ID_PATTERN)]
TicketId = Annotated[str, Path(pattern=TICKET_ID_PATTERN)]


def _run_and_check(
    session: Session, run_id: str, user: CurrentUser
) -> AiRunResponse:
    linked = AiRunRepository(session).get_for_ticket(run_id)
    if linked is None:
        raise AppError("AI_RUN_NOT_FOUND", "AI 任务不存在", 404, {"run_id": run_id})
    run, ticket = linked
    ensure_ticket_visible(user, ticket.submitter)
    return AiRunRepository.to_response(run)


@router.get("/ai-runs/{run_id}", response_model=AiRunResponse)
def get_ai_run(
    run_id: RunId,
    user: CurrentUser = Depends(require_auth),  # noqa: B008
    session: Session = Depends(get_db),  # noqa: B008
) -> AiRunResponse:
    return _run_and_check(session, run_id, user)


@router.post("/tickets/{ticket_id}/ai-runs", response_model=AiRunResponse, status_code=202)
def rerun_ticket_ai(
    ticket_id: TicketId,
    user: CurrentUser = Depends(require_operator),  # noqa: B008
    session: Session = Depends(get_db),  # noqa: B008
) -> AiRunResponse:
    ticket = TicketRepository(session).get(ticket_id)
    if ticket is None:
        raise AppError("TICKET_NOT_FOUND", "工单不存在", 404, {"ticket_id": ticket_id})
    run = AiRunRepository(session).create(ticket, get_settings(), user.id)
    response = AiRunRepository.to_response(run)
    session.commit()
    dispatch_ai_run(run.id)
    return response


@router.post("/ai-runs/{run_id}/decision", response_model=AiRunResponse)
def decide_ai_suggestion(
    run_id: RunId,
    request: AiRunDecisionRequest,
    user: CurrentUser = Depends(require_operator),  # noqa: B008
    session: Session = Depends(get_db),  # noqa: B008
) -> AiRunResponse:
    if user.id is None:
        raise AppError("AUTH_INVALID_TOKEN", "当前用户缺少数据库身份", 401, {})
    run = AiRunRepository(session).decide(run_id, request, user.id)
    return AiRunRepository.to_response(run)


@router.post("/ai-runs/recover-stale", response_model=StaleRecoveryResponse)
def recover_stale_ai_runs(
    _user: CurrentUser = Depends(require_operator),  # noqa: B008
    session: Session = Depends(get_db),  # noqa: B008
) -> StaleRecoveryResponse:
    settings = get_settings()
    run_ids = AiRunRepository(session).recover_stale(
        settings.ai_task_stale_seconds,
        settings.ai_task_max_retries,
    )
    session.commit()
    for run_id in run_ids:
        dispatch_ai_run(run_id)
    return StaleRecoveryResponse(recovered_run_ids=run_ids)


@router.websocket("/ai-runs/{run_id}/ws")
async def subscribe_ai_run(websocket: WebSocket, run_id: str) -> None:
    token = websocket.query_params.get("access_token", "")
    user = current_user_from_token(token)
    if user is None:
        await websocket.close(code=4401, reason="authentication required")
        return
    await websocket.accept()
    last_state: tuple | None = None
    try:
        while True:
            with session_scope() as session:
                response = _run_and_check(session, run_id, user)
            state = (response.status, response.stage, response.progress, response.updated_at)
            if state != last_state:
                await websocket.send_json(
                    AiRunStatusEvent(run=response).model_dump(mode="json")
                )
                last_state = state
            if response.status in {"completed", "failed", "cancelled"}:
                await websocket.close(code=1000)
                return
            await asyncio.sleep(0.25)
    except WebSocketDisconnect:
        return
    except AppError as exc:
        await websocket.send_json(
            {"type": "error", "error": {"code": exc.code, "message": exc.message}}
        )
        await websocket.close(code=4403 if exc.status_code == 403 else 4404)
