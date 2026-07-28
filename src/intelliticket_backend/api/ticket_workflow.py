from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path
from sqlalchemy.orm import Session

from intelliticket_backend.db import get_db
from intelliticket_backend.schemas.ticket_history import TICKET_ID_PATTERN
from intelliticket_backend.schemas.users import CurrentUser
from intelliticket_backend.schemas.workflow import (
    AssignTicketRequest,
    CancelTicketRequest,
    ClaimTicketRequest,
    ConfirmTicketRequest,
    ReopenTicketRequest,
    ResolveTicketRequest,
    SlaBreachesResponse,
    TicketCommentCreateRequest,
    TicketCommentResponse,
    TicketCommentsResponse,
    TicketTimelineResponse,
    TicketWorkflowResponse,
    TriageCompleteRequest,
)
from intelliticket_backend.services.auth import require_admin, require_auth, require_operator
from intelliticket_backend.services.ticket_workflow import TicketWorkflowService

router = APIRouter(prefix="/api/v1/tickets", tags=["ticket-workflow"])
TicketId = Annotated[str, Path(pattern=TICKET_ID_PATTERN)]


@router.get("/sla/overdue", response_model=SlaBreachesResponse)
def overdue_tickets(
    user: CurrentUser = Depends(require_operator),  # noqa: B008
    session: Session = Depends(get_db),  # noqa: B008
) -> SlaBreachesResponse:
    return TicketWorkflowService(session).overdue(user)


@router.get("/{ticket_id}/workflow", response_model=TicketWorkflowResponse)
def get_workflow_ticket(
    ticket_id: TicketId,
    user: CurrentUser = Depends(require_auth),  # noqa: B008
    session: Session = Depends(get_db),  # noqa: B008
) -> TicketWorkflowResponse:
    return TicketWorkflowService(session).get(ticket_id, user)


@router.post("/{ticket_id}/triage-complete", response_model=TicketWorkflowResponse)
def triage_complete(
    ticket_id: TicketId,
    request: TriageCompleteRequest,
    user: CurrentUser = Depends(require_operator),  # noqa: B008
    session: Session = Depends(get_db),  # noqa: B008
) -> TicketWorkflowResponse:
    return TicketWorkflowService(session).triage_complete(ticket_id, request, user)


@router.post("/{ticket_id}/claim", response_model=TicketWorkflowResponse)
def claim_ticket(
    ticket_id: TicketId,
    request: ClaimTicketRequest,
    user: CurrentUser = Depends(require_operator),  # noqa: B008
    session: Session = Depends(get_db),  # noqa: B008
) -> TicketWorkflowResponse:
    return TicketWorkflowService(session).claim(ticket_id, request.version, user)


@router.post("/{ticket_id}/assign", response_model=TicketWorkflowResponse)
def assign_ticket(
    ticket_id: TicketId,
    request: AssignTicketRequest,
    user: CurrentUser = Depends(require_admin),  # noqa: B008
    session: Session = Depends(get_db),  # noqa: B008
) -> TicketWorkflowResponse:
    return TicketWorkflowService(session).assign(ticket_id, request, user)


@router.get("/{ticket_id}/comments", response_model=TicketCommentsResponse)
def list_comments(
    ticket_id: TicketId,
    user: CurrentUser = Depends(require_auth),  # noqa: B008
    session: Session = Depends(get_db),  # noqa: B008
) -> TicketCommentsResponse:
    return TicketWorkflowService(session).comments(ticket_id, user)


@router.post("/{ticket_id}/comments", response_model=TicketCommentResponse, status_code=201)
def add_comment(
    ticket_id: TicketId,
    request: TicketCommentCreateRequest,
    user: CurrentUser = Depends(require_auth),  # noqa: B008
    session: Session = Depends(get_db),  # noqa: B008
) -> TicketCommentResponse:
    return TicketWorkflowService(session).add_comment(ticket_id, request, user)


@router.get("/{ticket_id}/timeline", response_model=TicketTimelineResponse)
def ticket_timeline(
    ticket_id: TicketId,
    user: CurrentUser = Depends(require_auth),  # noqa: B008
    session: Session = Depends(get_db),  # noqa: B008
) -> TicketTimelineResponse:
    return TicketWorkflowService(session).timeline(ticket_id, user)


@router.post("/{ticket_id}/resolve", response_model=TicketWorkflowResponse)
def resolve_ticket(
    ticket_id: TicketId,
    request: ResolveTicketRequest,
    user: CurrentUser = Depends(require_operator),  # noqa: B008
    session: Session = Depends(get_db),  # noqa: B008
) -> TicketWorkflowResponse:
    return TicketWorkflowService(session).resolve(ticket_id, request, user)


@router.post("/{ticket_id}/confirm", response_model=TicketWorkflowResponse)
def confirm_ticket(
    ticket_id: TicketId,
    request: ConfirmTicketRequest,
    user: CurrentUser = Depends(require_auth),  # noqa: B008
    session: Session = Depends(get_db),  # noqa: B008
) -> TicketWorkflowResponse:
    return TicketWorkflowService(session).confirm(ticket_id, request, user)


@router.post("/{ticket_id}/reopen", response_model=TicketWorkflowResponse)
def reopen_ticket(
    ticket_id: TicketId,
    request: ReopenTicketRequest,
    user: CurrentUser = Depends(require_auth),  # noqa: B008
    session: Session = Depends(get_db),  # noqa: B008
) -> TicketWorkflowResponse:
    return TicketWorkflowService(session).reopen(ticket_id, request, user)


@router.post("/{ticket_id}/cancel", response_model=TicketWorkflowResponse)
def cancel_ticket(
    ticket_id: TicketId,
    request: CancelTicketRequest,
    user: CurrentUser = Depends(require_auth),  # noqa: B008
    session: Session = Depends(get_db),  # noqa: B008
) -> TicketWorkflowResponse:
    return TicketWorkflowService(session).cancel(ticket_id, request, user)
