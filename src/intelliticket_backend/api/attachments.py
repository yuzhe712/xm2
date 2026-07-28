from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Path, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from intelliticket_backend.config import get_settings
from intelliticket_backend.db import get_db
from intelliticket_backend.errors import AppError
from intelliticket_backend.models import Attachment, Ticket
from intelliticket_backend.repositories.attachments import AttachmentRepository
from intelliticket_backend.repositories.tickets import TicketRepository
from intelliticket_backend.schemas.attachments import AttachmentListResponse, AttachmentResponse
from intelliticket_backend.schemas.ticket_history import TICKET_ID_PATTERN
from intelliticket_backend.schemas.users import CurrentUser
from intelliticket_backend.services.attachments import LocalAttachmentStorage
from intelliticket_backend.services.auth import require_auth

router = APIRouter(prefix="/api/v1/tickets", tags=["attachments"])
TicketId = Annotated[str, Path(pattern=TICKET_ID_PATTERN)]


def _storage() -> LocalAttachmentStorage:
    settings = get_settings()
    return LocalAttachmentStorage(settings.attachment_storage_dir, settings.attachment_max_bytes)


def _visible_ticket(session: Session, ticket_id: str, actor: CurrentUser) -> Ticket:
    ticket = TicketRepository(session).get(ticket_id)
    if ticket is None:
        raise AppError("TICKET_NOT_FOUND", "工单不存在", 404, {"ticket_id": ticket_id})
    if actor.role not in {"operator", "admin"} and ticket.submitter_id != actor.id:
        raise AppError("TICKET_ACCESS_DENIED", "无权查看该工单", 403, {})
    return ticket


def _response(attachment: Attachment) -> AttachmentResponse:
    return AttachmentResponse(
        id=attachment.id,
        ticket_id=attachment.ticket_id,
        uploader_id=attachment.uploader_id,
        original_name=attachment.original_name,
        content_type=attachment.content_type,
        size_bytes=attachment.size_bytes,
        sha256=attachment.sha256,
        created_at=attachment.created_at.isoformat(),
    )


@router.post("/{ticket_id}/attachments", response_model=AttachmentResponse, status_code=201)
def upload_attachment(
    ticket_id: TicketId,
    file: UploadFile = File(...),  # noqa: B008
    actor: CurrentUser = Depends(require_auth),  # noqa: B008
    session: Session = Depends(get_db),  # noqa: B008
) -> AttachmentResponse:
    ticket = _visible_ticket(session, ticket_id, actor)
    if actor.id is None:
        raise AppError("AUTH_INVALID_TOKEN", "当前用户缺少数据库身份", 401, {})
    storage = _storage()
    stored = storage.store(file.filename, file.content_type, file.file)
    try:
        attachment = AttachmentRepository(session).create(
            ticket_id=ticket_id,
            uploader_id=actor.id,
            original_name=stored.original_name,
            storage_key=stored.storage_key,
            content_type=stored.content_type,
            size_bytes=stored.size_bytes,
            sha256=stored.sha256,
        )
        TicketRepository(session).add_event(
            ticket_id=ticket_id,
            actor_id=actor.id,
            event_type="attachment_uploaded",
            from_status=ticket.ticket_status,
            to_status=ticket.ticket_status,
            visibility="public",
            payload={
                "attachment_id": attachment.id,
                "name": attachment.original_name,
                "size_bytes": attachment.size_bytes,
            },
        )
        session.commit()
    except Exception:
        session.rollback()
        storage.delete(stored.storage_key)
        raise
    return _response(attachment)


@router.get("/{ticket_id}/attachments", response_model=AttachmentListResponse)
def list_attachments(
    ticket_id: TicketId,
    actor: CurrentUser = Depends(require_auth),  # noqa: B008
    session: Session = Depends(get_db),  # noqa: B008
) -> AttachmentListResponse:
    _visible_ticket(session, ticket_id, actor)
    return AttachmentListResponse(
        items=[_response(item) for item in AttachmentRepository(session).list_for_ticket(ticket_id)]
    )


@router.get("/{ticket_id}/attachments/{attachment_id}", response_class=FileResponse)
def download_attachment(
    ticket_id: TicketId,
    attachment_id: str,
    actor: CurrentUser = Depends(require_auth),  # noqa: B008
    session: Session = Depends(get_db),  # noqa: B008
) -> FileResponse:
    _visible_ticket(session, ticket_id, actor)
    attachment = AttachmentRepository(session).get_for_ticket(attachment_id, ticket_id)
    if attachment is None:
        raise AppError("ATTACHMENT_NOT_FOUND", "附件不存在", 404, {})
    return FileResponse(
        _storage().path_for(attachment.storage_key),
        media_type=attachment.content_type,
        filename=attachment.original_name,
    )
