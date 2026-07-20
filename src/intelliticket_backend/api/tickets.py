from __future__ import annotations

import asyncio
from queue import Queue
from threading import Event, Thread
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, WebSocket, WebSocketDisconnect, status
from pydantic import ValidationError

from intelliticket_backend.config import get_settings
from intelliticket_backend.errors import AppError
from intelliticket_backend.repositories.ticket_history import TicketHistoryRepository
from intelliticket_backend.schemas.ticket_history import (
    TICKET_ID_PATTERN,
    SupportReplyDraftUpdateRequest,
    TicketHistoryDetailResponse,
    TicketHistoryListResponse,
    TicketLifecycleUpdateRequest,
)
from intelliticket_backend.schemas.tickets import (
    DeskId,
    TicketProcessRequest,
    TicketProcessResponse,
    TicketProcessWsCancelledEvent,
    TicketProcessWsCompletedEvent,
    TicketProcessWsErrorEvent,
    TicketProcessWsStartedEvent,
    TicketProcessWsStartMessage,
    TicketSubmitRequest,
    TicketSubmitResponse,
)
from intelliticket_backend.schemas.users import CurrentUser
from intelliticket_backend.services.auth import require_auth, require_operator
from intelliticket_backend.services.notifications import (
    NotificationService,
)
from intelliticket_backend.services.ticket_processing import TicketProcessingService

router = APIRouter(prefix="/api/v1/tickets", tags=["tickets"])

knowledge_router = APIRouter(prefix="/api/v1/knowledge", tags=["knowledge"])


@knowledge_router.get("/stats")
def knowledge_stats() -> dict:
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


@router.get("", response_model=TicketHistoryListResponse)
def list_tickets(
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    desk_id: Annotated[DeskId | None, Query()] = None,
) -> TicketHistoryListResponse:
    """查询已持久化的工单历史。"""
    return _history_repository().list_tickets(limit=limit, offset=offset, desk_id=desk_id)


@router.post("/submit", response_model=TicketSubmitResponse)
def submit_ticket(
    request: TicketSubmitRequest,
    user: CurrentUser = Depends(require_auth),  # noqa: B008
) -> TicketSubmitResponse:
    """员工提交工单（只创建，不处理）。提交后通知运维群。"""
    service = TicketProcessingService()
    ticket_id = service._make_id("TCK")
    result = service.history_repository.save_pending_ticket(
        ticket_id=ticket_id,
        text=request.text,
        data_mode=request.data_mode.value,
        desk_id=request.desk_id.value,
        submitter=user.user_id,
    )
    _notify_operator_new_ticket(ticket_id=ticket_id, submitter=user.user_id, text=request.text)
    return TicketSubmitResponse.model_validate(result)


@router.get("/mine", response_model=TicketHistoryListResponse)
def list_my_tickets(
    user: CurrentUser = Depends(require_auth),  # noqa: B008
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    desk_id: Annotated[DeskId | None, Query()] = None,
) -> TicketHistoryListResponse:
    """当前登录用户查看自己提交的工单。"""
    return _history_repository().list_by_submitter(
        user.user_id, limit=limit, offset=offset, desk_id=desk_id,
    )


@router.get("/queue", response_model=TicketHistoryListResponse)
def list_pending_queue(
    _user: CurrentUser = Depends(require_operator),  # noqa: B008
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> TicketHistoryListResponse:
    """运维查看待处理工单队列（需 operator 角色）。"""
    return _history_repository().list_pending(limit=limit, offset=offset)


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
            data_mode=current.data_mode,
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
            data_mode=current.data_mode,
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
    """更新工单业务生命周期。状态变为 resolved 时通知提交人。"""
    repository = _history_repository()
    result = repository.update_ticket_lifecycle(ticket_id, request)
    if result is None:
        raise AppError(
            "TICKET_NOT_FOUND",
            "未找到已持久化的工单",
            status.HTTP_404_NOT_FOUND,
            {"ticket_id": ticket_id},
        )
    if request.ticket_status == "resolved" and result.submitter:
        _notify_employee_resolved(
            ticket_id=ticket_id,
            submitter=result.submitter,
            resolution=result.resolution_summary or "已处理完成",
        )
    return result


def _notify_operator_new_ticket(ticket_id: str, submitter: str, text: str) -> None:
    """员工提交工单后，通知运维群有新工单待处理。"""
    settings = get_settings()
    if not settings.dingtalk_enabled or settings.dingtalk_operator_webhook_url is None:
        return
    try:
        from intelliticket_backend.services.notifications import (
            DingTalkNotifier,
            NotificationPayload,
        )

        notifier = DingTalkNotifier(
            webhook_url=settings.dingtalk_operator_webhook_url
        )
        svc = NotificationService(notifiers=[notifier])
        svc.send(
            NotificationPayload(
                ticket_id=ticket_id,
                title=f"新工单 {ticket_id}",
                summary=f"{submitter} 提交了工单：\n\n{text}",
                priority="P3",
                affected_service=None,
                recommended_actions=[],
            )
        )
    except Exception:
        pass


def _notify_employee_resolved(
    ticket_id: str, submitter: str, resolution: str
) -> None:
    settings = get_settings()
    if not settings.dingtalk_enabled or settings.dingtalk_employee_webhook_url is None:
        return
    try:
        from intelliticket_backend.services.notifications import (
            DingTalkNotifier,
            NotificationPayload,
        )

        notifier = DingTalkNotifier(
            webhook_url=settings.dingtalk_employee_webhook_url
        )
        svc = NotificationService(notifiers=[notifier])
        svc.send(
            NotificationPayload(
                ticket_id=ticket_id,
                title="工单已解决",
                summary=f"您的工单 {ticket_id} 已由运维人员处理完成。\n处理结果：{resolution}",
                priority="P3",
                affected_service=None,
                recommended_actions=[],
            )
        )
    except Exception:
        pass


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
) -> TicketHistoryDetailResponse:
    """按 ticket_id 查询已持久化的工单详情。"""
    result = _history_repository().get_ticket(ticket_id)
    if result is None:
        raise AppError(
            "TICKET_NOT_FOUND",
            "未找到已持久化的工单",
            status.HTTP_404_NOT_FOUND,
            {"ticket_id": ticket_id},
        )
    return result


@router.post("/process", response_model=TicketProcessResponse)
def process_ticket(
    request: TicketProcessRequest,
    user: CurrentUser = Depends(require_operator),  # noqa: B008
) -> TicketProcessResponse:
    """处理自然语言运维告警工单。AI 诊断后自动归属给当前运维。"""
    request.operator_id = user.user_id
    return TicketProcessingService().process_ticket(request)


@router.websocket("/process/ws")
async def process_ticket_ws(websocket: WebSocket) -> None:
    """通过 WebSocket 处理工单并推送 Agent 进度事件。"""
    await websocket.accept()
    sequence = 0
    ticket_id = TicketProcessingService()._make_id("TCK")
    run_id = TicketProcessingService()._make_id("RUN")
    cancel_event = Event()

    try:
        raw_start = await websocket.receive_json()
        start = TicketProcessWsStartMessage.model_validate(raw_start)
    except (ValidationError, ValueError) as exc:
        sequence += 1
        await websocket.send_json(
            TicketProcessWsErrorEvent(
                ticket_id=ticket_id,
                run_id=run_id,
                sequence=sequence,
                error={
                    "code": "WS_INVALID_START_MESSAGE",
                    "message": "WebSocket start 消息无效",
                    "details": {"error": str(exc)},
                },
            ).model_dump(mode="json")
        )
        await websocket.close(code=1003)
        return

    sequence += 1
    await websocket.send_json(
        TicketProcessWsStartedEvent(
            ticket_id=ticket_id,
            run_id=run_id,
            sequence=sequence,
        ).model_dump(mode="json")
    )

    queue: Queue[dict] = Queue(maxsize=16)

    def progress_sink(event: object) -> None:
        try:
            queue.put_nowait(event.model_dump(mode="json"))
        except Exception as exc:  # pragma: no cover - defensive bridge guard
            cancel_event.set()
            raise AppError(
                "STREAM_BACKPRESSURE",
                "WebSocket 进度事件队列已满",
                500,
                {"error": str(exc)},
            ) from exc

    def run_processing() -> None:
        try:
            result = TicketProcessingService().process_ticket(
                TicketProcessRequest(
                    text=start.request.text,
                    data_mode=start.request.data_mode,
                    desk_id=start.request.desk_id,
                ),
                progress_sink=progress_sink,
                cancel_event=cancel_event,
                ticket_id=ticket_id,
                run_id=run_id,
            )
            queue.put_nowait({"type": "__completed__", "result": result.model_dump(mode="json")})
        except AppError as exc:
            queue.put_nowait(
                {
                    "type": "__error__",
                    "error": {"code": exc.code, "message": exc.message, "details": exc.details},
                }
            )
        except Exception as exc:  # pragma: no cover - global safety net
            queue.put_nowait(
                {
                    "type": "__error__",
                    "error": {
                        "code": "WS_PROCESSING_ERROR",
                        "message": "WebSocket 工单处理失败",
                        "details": {"error": str(exc)},
                    },
                }
            )

    worker = Thread(target=run_processing, daemon=True)
    worker.start()

    try:
        while True:
            try:
                client_message = await asyncio.wait_for(websocket.receive_json(), timeout=0.01)
                if client_message.get("type") == "cancel":
                    cancel_event.set()
            except TimeoutError:
                pass
            except WebSocketDisconnect:
                cancel_event.set()
                return

            try:
                item = queue.get_nowait()
            except Exception:
                await asyncio.sleep(0.01)
                continue

            if item.get("type") == "__completed__":
                sequence += 1
                await websocket.send_json(
                    TicketProcessWsCompletedEvent(
                        ticket_id=ticket_id,
                        run_id=run_id,
                        sequence=sequence,
                        result=TicketProcessResponse.model_validate(item["result"]),
                    ).model_dump(mode="json")
                )
                await websocket.close(code=1000)
                return

            if item.get("type") == "__error__":
                if item["error"]["code"] == "PROCESSING_CANCELLED":
                    sequence += 1
                    await websocket.send_json(
                        TicketProcessWsCancelledEvent(
                            ticket_id=ticket_id,
                            run_id=run_id,
                            sequence=sequence,
                        ).model_dump(mode="json")
                    )
                    await websocket.close(code=1000)
                    return
                sequence += 1
                await websocket.send_json(
                    TicketProcessWsErrorEvent(
                        ticket_id=ticket_id,
                        run_id=run_id,
                        sequence=sequence,
                        error=item["error"],
                    ).model_dump(mode="json")
                )
                await websocket.close(code=1011)
                return

            await websocket.send_json(item)
    finally:
        cancel_event.set()
