from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from intelliticket_backend.models import Attachment


class AttachmentRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        *,
        ticket_id: str,
        uploader_id: str,
        original_name: str,
        storage_key: str,
        content_type: str,
        size_bytes: int,
        sha256: str,
    ) -> Attachment:
        attachment = Attachment(
            ticket_id=ticket_id,
            uploader_id=uploader_id,
            original_name=original_name,
            storage_key=storage_key,
            content_type=content_type,
            size_bytes=size_bytes,
            sha256=sha256,
        )
        self.session.add(attachment)
        self.session.flush()
        return attachment

    def get_for_ticket(self, attachment_id: str, ticket_id: str) -> Attachment | None:
        return self.session.scalar(
            select(Attachment).where(
                Attachment.id == attachment_id,
                Attachment.ticket_id == ticket_id,
            )
        )

    def list_for_ticket(self, ticket_id: str) -> list[Attachment]:
        return list(
            self.session.scalars(
                select(Attachment)
                .where(Attachment.ticket_id == ticket_id)
                .order_by(Attachment.created_at, Attachment.id)
            ).all()
        )
