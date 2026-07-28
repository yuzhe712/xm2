from __future__ import annotations

from fastapi import status

from intelliticket_backend.errors import AppError
from intelliticket_backend.schemas.users import CurrentUser


def ensure_ticket_visible(user: CurrentUser, submitter: str | None) -> None:
    if user.role in {"operator", "admin"}:
        return
    if submitter == user.user_id:
        return
    raise AppError(
        "TICKET_ACCESS_DENIED",
        "无权查看该工单",
        status.HTTP_403_FORBIDDEN,
        {},
    )
