from __future__ import annotations

from pydantic import BaseModel


class AttachmentResponse(BaseModel):
    id: str
    ticket_id: str
    uploader_id: str
    original_name: str
    content_type: str
    size_bytes: int
    sha256: str
    created_at: str


class AttachmentListResponse(BaseModel):
    items: list[AttachmentResponse]
