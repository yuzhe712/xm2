from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, WebSocket, status
from sqlalchemy.orm import Session

from intelliticket_backend.config import get_settings
from intelliticket_backend.db import get_db
from intelliticket_backend.errors import AppError
from intelliticket_backend.models import Ticket
from intelliticket_backend.repositories.ai_runs import AiRunRepository
from intelliticket_backend.repositories.ticket_history import TicketHistoryRepository
from intelliticket_backend.repositories.tickets import TicketRepository
from intelliticket_backend.schemas.ticket_history import (
    TICKET_ID_PATTERN,
    SupportReplyDraftUpdateRequest,
    TicketHistoryDetailResponse,
    TicketHistoryListResponse,
    TicketHistorySummary,
    TicketLifecycleUpdateRequest,
)
from intelliticket_backend.schemas.tickets import (
    DataMode,
    DeskId,
    TicketProcessRequest,
    TicketProcessResponse,
    TicketSubmitRequest,
    TicketSubmitResponse,
)
from intelliticket_backend.schemas.users import CurrentUser
from intelliticket_backend.services.auth import (
    current_user_from_token,
    require_auth,
    require_operator,
)
from intelliticket_backend.services.notifications import (
    NotificationPayload,
    queue_notification,
)
from intelliticket_backend.services.permissions import ensure_ticket_visible
from intelliticket_backend.services.ticket_processing import TicketProcessingService
from intelliticket_backend.services.ticket_workflow import TicketWorkflowService
from intelliticket_backend.services.worker_tasks import dispatch_ai_run, dispatch_notification

router = APIRouter(prefix="/api/v1/tickets", tags=["tickets"])

knowledge_router = APIRouter(prefix="/api/v1/knowledge", tags=["knowledge"])


@knowledge_router.get("/stats")
def knowledge_stats(
    _user: CurrentUser = Depends(require_operator),  # noqa: B008
) -> dict:
    """知识库统计：案例总数、已确认数、建议 SOP 主题。"""
    from intelliticket_backend.services.case_retrieval import CaseRecord, CaseRetrieval, _tokenize

    retrieval = CaseRetrieval()
    repo = _history_repository()
    for case_data in repo.load_all_cases():
        import json as _json

        symptoms = (
            _json.loads(case_data["symptoms_json"])
            if isinstance(case_data.get("symptoms_json"), str)
            else (case_data.get("symptoms_json") or [])
        )
        from collections import Counter

        record = CaseRecord(
            ticket_id=case_data["ticket_id"],
            text=case_data["input_text"],
            symptoms=symptoms,
            data_mode=case_data.get("data_mode", "mock"),
            root_cause=case_data.get("root_cause", ""),
            confirmed_root_cause=case_data.get("confirmed_root_cause", ""),
            resolution=case_data.get("resolution", ""),
        )
        record.token_counts = Counter(
            _tokenize(case_data["input_text"])
            + [t for s in symptoms for t in _tokenize(s)]
        )
        retrieval.index(record)
    retrieval.rebuild()
    return retrieval.stats()


def _history_repository() -> TicketHistoryRepository:
    return TicketHistoryRepository(get_settings().ticket_history_db_path)


def _configured_data_mode() -> DataMode:
    return DataMode(get_settings().data_mode)


def _merged_listing(
    sql_items: list,
    legacy_items: list,
    *,
    limit: int,
    offset: int,
) -> TicketHistoryListResponse:
    by_id = {item.ticket_id: item for item in legacy_items}
    by_id.update({item.ticket_id: item for item in sql_items})
    items = sorted(
        by_id.values(),
        key=lambda item: (item.updated_at, item.ticket_id),
        reverse=True,
    )
    return TicketHistoryListResponse(
        items=items[offset : offset + limit],
        limit=limit,
        offset=offset,
        total=len(items),
    )


def _sql_history_summary(session: Session, ticket: Ticket) -> TicketHistorySummary:
    ai_run = (
        AiRunRepository(session).get(ticket.latest_run_id)
        if ticket.latest_run_id
        else None
    )
    return TicketRepository.to_history_summary(
        ticket,
        ai_status=ai_run.status if ai_run else "pending",
    )


@router.get("", response_model=TicketHistoryListResponse)
def list_tickets(
    _user: CurrentUser = Depends(require_operator),  # noqa: B008
    session: Session = Depends(get_db),  # noqa: B008
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    desk_id: Annotated[DeskId | None, Query()] = None,
) -> TicketHistoryListResponse:
    """查询已持久化的工单历史。"""
    sql_items = [
        _sql_history_summary(session, ticket)
        for ticket in TicketRepository(session).list_models(
            desk_id=desk_id.value if desk_id else None
        )
    ]
    legacy_repository = _history_repository()
    legacy_count = legacy_repository.list_tickets(
        limit=1, offset=0, desk_id=desk_id
    ).total
    legacy_items = legacy_repository.list_tickets(
        limit=max(legacy_count, 1), offset=0, desk_id=desk_id
    ).items
    return _merged_listing(sql_items, legacy_items, limit=limit, offset=offset)


@router.post("/submit", response_model=TicketSubmitResponse)
def submit_ticket(
    request: TicketSubmitRequest,
    user: CurrentUser = Depends(require_auth),  # noqa: B008
    session: Session = Depends(get_db),  # noqa: B008
) -> TicketSubmitResponse:
    """员工提交工单（只创建，不处理）。提交后通知运维群。"""
    title = request.title or request.text.splitlines()[0][:120]
    result = TicketWorkflowService(session).submit(
        title=title,
        description=request.text,
        data_mode=_configured_data_mode().value,
        desk_id=request.desk_id.value,
        submitter=user,
        priority=request.priority.value,
    )
    ticket = TicketRepository(session).get(result.ticket_id)
    assert ticket is not None
    ai_run = AiRunRepository(session).create(ticket, get_settings(), user.id)
    notification_id = queue_notification(
        session,
        ticket_id=result.ticket_id,
        target="operator",
        event_type="ticket_created",
        payload=NotificationPayload(
            ticket_id=result.ticket_id,
            title=f"新工单 {result.ticket_id}",
            summary=f"{user.user_id} 提交了工单：\n\n{request.text}",
            priority=request.priority.value,
            affected_service=None,
        ),
    )
    session.commit()
    task_id = dispatch_ai_run(ai_run.id)
    if notification_id is not None:
        dispatch_notification(notification_id)
    return TicketSubmitResponse(
        ticket_id=result.ticket_id,
        status=result.status,
        created_at=result.created_at,
        text=result.description,
        desk_id=result.desk_id,
        submitter=result.submitter,
        version=result.version,
        response_due_at=result.response_due_at,
        resolution_due_at=result.resolution_due_at,
        ai_run_id=ai_run.id,
        ai_status="queued" if task_id is not None else "failed",
    )


@router.get("/mine", response_model=TicketHistoryListResponse)
def list_my_tickets(
    user: CurrentUser = Depends(require_auth),  # noqa: B008
    session: Session = Depends(get_db),  # noqa: B008
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    desk_id: Annotated[DeskId | None, Query()] = None,
) -> TicketHistoryListResponse:
    """当前登录用户查看自己提交的工单。"""
    sql_items = [
        _sql_history_summary(session, ticket)
        for ticket in TicketRepository(session).list_models(
            desk_id=desk_id.value if desk_id else None,
            submitter_id=user.id,
        )
    ]
    legacy_repository = _history_repository()
    legacy_count = legacy_repository.list_by_submitter(
        user.user_id, limit=1, offset=0, desk_id=desk_id
    ).total
    legacy_items = legacy_repository.list_by_submitter(
        user.user_id, limit=max(legacy_count, 1), offset=0, desk_id=desk_id
    ).items
    return _merged_listing(sql_items, legacy_items, limit=limit, offset=offset)


@router.get("/queue", response_model=TicketHistoryListResponse)
def list_pending_queue(
    _user: CurrentUser = Depends(require_operator),  # noqa: B008
    session: Session = Depends(get_db),  # noqa: B008
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> TicketHistoryListResponse:
    """运维查看待处理工单队列（需 operator 角色）。"""
    sql_items = [
        _sql_history_summary(session, ticket)
        for ticket in TicketRepository(session).list_models(statuses={"pending", "open"})
    ]
    legacy_repository = _history_repository()
    legacy_count = legacy_repository.list_pending(limit=1, offset=0).total
    legacy_items = legacy_repository.list_pending(
        limit=max(legacy_count, 1), offset=0
    ).items
    return _merged_listing(sql_items, legacy_items, limit=limit, offset=offset)


@router.patch("/{ticket_id}/support-reply-draft", response_model=TicketHistoryDetailResponse)
def update_support_reply_draft(
    ticket_id: Annotated[str, Path(pattern=TICKET_ID_PATTERN)],
    request: SupportReplyDraftUpdateRequest,
    _user: CurrentUser = Depends(require_operator),  # noqa: B008
) -> TicketHistoryDetailResponse:
    """保存内部支持回复草稿；仅表示本地/mock 工作流状态。"""
    result = _history_repository().upsert_support_reply_draft(ticket_id, request)
    if result is None:
        raise AppError(
            "TICKET_NOT_FOUND",
            "未找到已持久化的工单",
            status.HTTP_404_NOT_FOUND,
            {"ticket_id": ticket_id},
        )
    return result


@router.post("/{ticket_id}/reprocess/preview", response_model=TicketProcessResponse)
def preview_reprocess_ticket(
    ticket_id: Annotated[str, Path(pattern=TICKET_ID_PATTERN)],
    user: CurrentUser = Depends(require_operator),  # noqa: B008
) -> TicketProcessResponse:
    """预览重新处理结果，不更新该工单 latest_run。"""
    current = _history_repository().get_ticket(ticket_id)
    if current is None:
        raise AppError(
            "TICKET_NOT_FOUND",
            "未找到已持久化的工单",
            status.HTTP_404_NOT_FOUND,
            {"ticket_id": ticket_id},
        )
    return TicketProcessingService().process_ticket_preview(
        TicketProcessRequest(
            text=current.input_text,
            data_mode=_configured_data_mode(),
            desk_id=current.desk_id,
            operator_id=user.user_id,
        ),
        ticket_id=ticket_id,
    )


@router.post("/{ticket_id}/reprocess", response_model=TicketHistoryDetailResponse)
def reprocess_ticket(
    ticket_id: Annotated[str, Path(pattern=TICKET_ID_PATTERN)],
    user: CurrentUser = Depends(require_operator),  # noqa: B008
) -> TicketHistoryDetailResponse:
    """在同一个 ticket_id 下重新处理工单并刷新 latest_run。"""
    repository = _history_repository()
    current = repository.get_ticket(ticket_id)
    if current is None:
        raise AppError(
            "TICKET_NOT_FOUND",
            "未找到已持久化的工单",
            status.HTTP_404_NOT_FOUND,
            {"ticket_id": ticket_id},
        )
    TicketProcessingService().process_ticket(
        TicketProcessRequest(
            text=current.input_text,
            data_mode=_configured_data_mode(),
            desk_id=current.desk_id,
            operator_id=user.user_id,
        ),
        ticket_id=ticket_id,
    )
    refreshed = repository.get_ticket(ticket_id)
    if refreshed is None:  # pragma: no cover - defensive consistency guard
        raise AppError(
            "TICKET_NOT_FOUND",
            "重新处理后未找到工单详情",
            status.HTTP_404_NOT_FOUND,
            {"ticket_id": ticket_id},
        )
    return refreshed


@router.patch("/{ticket_id}", response_model=TicketHistoryDetailResponse)
def update_ticket_lifecycle(
    ticket_id: Annotated[str, Path(pattern=TICKET_ID_PATTERN)],
    request: TicketLifecycleUpdateRequest,
    user: CurrentUser = Depends(require_operator),  # noqa: B008
) -> TicketHistoryDetailResponse:
    """兼容旧 AI 记录的非状态字段；状态只能通过独立工作流命令变更。"""
    repository = _history_repository()
    if repository.get_ticket(ticket_id) is None:
        raise AppError(
            "TICKET_NOT_FOUND",
            "未找到已持久化的工单",
            status.HTTP_404_NOT_FOUND,
            {"ticket_id": ticket_id},
        )
    if request.ticket_status is not None:
        raise AppError(
            "TICKET_COMMAND_REQUIRED",
            "请使用认领、解决、确认、重开或取消命令变更工单状态",
            status.HTTP_409_CONFLICT,
            {"requested_status": request.ticket_status},
        )
    result = repository.update_ticket_lifecycle(ticket_id, request)
    if result is None:
        raise AppError(
            "TICKET_NOT_FOUND",
            "未找到已持久化的工单",
            status.HTTP_404_NOT_FOUND,
            {"ticket_id": ticket_id},
        )
    return result


@router.patch("/{ticket_id}/feedback", response_model=TicketHistoryDetailResponse)
def confirm_root_cause(
    ticket_id: Annotated[str, Path(pattern=TICKET_ID_PATTERN)],
    request: TicketLifecycleUpdateRequest,
    user: CurrentUser = Depends(require_operator),  # noqa: B008
) -> TicketHistoryDetailResponse:
    """运维确认工单根因并反馈到案例库，提升未来诊断准确率。"""
    repository = _history_repository()
    result = repository.update_ticket_lifecycle(ticket_id, request)
    if result is None:
        raise AppError(
            "TICKET_NOT_FOUND",
            "未找到已持久化的工单",
            status.HTTP_404_NOT_FOUND,
            {"ticket_id": ticket_id},
        )
    if request.root_cause:
        repository.confirm_case(
            ticket_id=ticket_id,
            confirmed_root_cause=request.root_cause,
            resolution=(request.fix_action or ""),
        )
    return result


@router.get("/{ticket_id}", response_model=TicketHistoryDetailResponse)
def get_ticket(
    ticket_id: Annotated[str, Path(pattern=TICKET_ID_PATTERN)],
    user: CurrentUser = Depends(require_auth),  # noqa: B008
    session: Session = Depends(get_db),  # noqa: B008
) -> TicketHistoryDetailResponse:
    """按 ticket_id 查询已持久化的工单详情。"""
    sql_ticket = TicketRepository(session).get(ticket_id)
    if sql_ticket is not None:
        ensure_ticket_visible(user, sql_ticket.submitter)
        ai_run = (
            AiRunRepository(session).get(sql_ticket.latest_run_id)
            if sql_ticket.latest_run_id
            else None
        )
        return TicketRepository.to_history_detail(sql_ticket, ai_run)
    result = _history_repository().get_ticket(ticket_id)
    if result is None:
        raise AppError(
            "TICKET_NOT_FOUND",
            "未找到已持久化的工单",
            status.HTTP_404_NOT_FOUND,
            {"ticket_id": ticket_id},
        )
    ensure_ticket_visible(user, result.submitter)
    return result


@router.post("/process", response_model=TicketProcessResponse)
def process_ticket(
    request: TicketProcessRequest,
    user: CurrentUser = Depends(require_operator),  # noqa: B008
) -> TicketProcessResponse:
    """处理自然语言运维告警工单。AI 诊断后自动归属给当前运维。"""
    request.data_mode = _configured_data_mode()
    request.operator_id = user.user_id
    return TicketProcessingService().process_ticket(request)


@router.websocket("/process/ws")
async def process_ticket_ws(websocket: WebSocket) -> None:
    """Deprecated start-and-process socket; use the persistent ai-run subscription."""
    token = websocket.query_params.get("access_token", "")
    user = current_user_from_token(token)
    if user is None:
        await websocket.close(code=4401, reason="authentication required")
        return
    if user.role not in {"operator", "admin"}:
        await websocket.close(code=4403, reason="operator role required")
        return
    await websocket.accept()
    await websocket.send_json(
        {
            "type": "error",
            "error": {
                "code": "WS_PROCESSING_DEPRECATED",
                "message": "请先创建工单，再订阅 /api/v1/ai-runs/{run_id}/ws",
                "details": {},
            },
        }
    )
    await websocket.close(code=1008, reason="persistent ai-run subscription required")
