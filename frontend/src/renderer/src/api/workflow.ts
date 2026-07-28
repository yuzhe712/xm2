import type { TicketHistoryListResponse, TicketSubmitRequest, TicketSubmitResponse } from '../types/tickets'
import type { AiRun, CommentVisibility, TicketComment, TicketEvent, TicketDetailRecord, WorkflowTicket } from '../types/workflow'
import { apiRequest } from './client'

function command<T>(ticketId: string, action: string, body: object, token: string): Promise<T> {
  return apiRequest<T>(`/api/v1/tickets/${encodeURIComponent(ticketId)}/${action}`, {
    method: 'POST',
    body: JSON.stringify(body),
  }, token)
}

export function submitNewTicket(request: TicketSubmitRequest, token: string): Promise<TicketSubmitResponse> {
  return apiRequest('/api/v1/tickets/submit', {
    method: 'POST',
    body: JSON.stringify(request),
  }, token)
}

export function listMine(token: string): Promise<TicketHistoryListResponse> {
  return apiRequest('/api/v1/tickets/mine?limit=100&offset=0', {}, token)
}

export function listQueue(token: string): Promise<TicketHistoryListResponse> {
  return apiRequest('/api/v1/tickets/queue?limit=100&offset=0', {}, token)
}

export function listAllTickets(token: string): Promise<TicketHistoryListResponse> {
  return apiRequest('/api/v1/tickets?limit=100&offset=0', {}, token)
}

export function getWorkflowTicket(ticketId: string, token: string): Promise<WorkflowTicket> {
  return apiRequest(`/api/v1/tickets/${encodeURIComponent(ticketId)}/workflow`, {}, token)
}

export function getTicketRecord(ticketId: string, token: string): Promise<TicketDetailRecord> {
  return apiRequest(`/api/v1/tickets/${encodeURIComponent(ticketId)}`, {}, token)
}

export async function getComments(ticketId: string, token: string): Promise<TicketComment[]> {
  const response = await apiRequest<{ items: TicketComment[] }>(
    `/api/v1/tickets/${encodeURIComponent(ticketId)}/comments`, {}, token,
  )
  return response.items
}

export async function getTimeline(ticketId: string, token: string): Promise<TicketEvent[]> {
  const response = await apiRequest<{ items: TicketEvent[] }>(
    `/api/v1/tickets/${encodeURIComponent(ticketId)}/timeline`, {}, token,
  )
  return response.items
}

export function addComment(
  ticketId: string,
  version: number,
  body: string,
  visibility: CommentVisibility,
  token: string,
): Promise<TicketComment> {
  return command(ticketId, 'comments', { version, body, visibility }, token)
}

export function claimTicket(ticketId: string, version: number, token: string): Promise<WorkflowTicket> {
  return command(ticketId, 'claim', { version }, token)
}

export function acceptTicket(
  ticketId: string,
  version: number,
  category: string,
  priority: string,
  affectedService: string,
  token: string,
): Promise<WorkflowTicket> {
  return command(ticketId, 'triage-complete', {
    version,
    category,
    priority,
    affected_service: affectedService || null,
  }, token)
}

export function resolveTicket(
  ticketId: string,
  version: number,
  values: { resolution_summary: string; root_cause: string; fix_action: string; verification: string },
  token: string,
): Promise<WorkflowTicket> {
  return command(ticketId, 'resolve', { version, ...values }, token)
}

export function confirmTicket(ticketId: string, version: number, token: string): Promise<WorkflowTicket> {
  return command(ticketId, 'confirm', { version }, token)
}

export function reopenTicket(ticketId: string, version: number, reason: string, token: string): Promise<WorkflowTicket> {
  return command(ticketId, 'reopen', { version, reason }, token)
}

export function cancelTicket(ticketId: string, version: number, reason: string, token: string): Promise<WorkflowTicket> {
  return command(ticketId, 'cancel', { version, reason }, token)
}

export function getAiRun(runId: string, token: string): Promise<AiRun> {
  return apiRequest(`/api/v1/ai-runs/${encodeURIComponent(runId)}`, {}, token)
}

export function rerunAi(ticketId: string, token: string): Promise<AiRun> {
  return apiRequest(`/api/v1/tickets/${encodeURIComponent(ticketId)}/ai-runs`, { method: 'POST' }, token)
}

export function decideAiRun(
  runId: string,
  decision: 'accepted' | 'modified' | 'rejected',
  note: string,
  modifiedResult: Record<string, unknown> | null,
  token: string,
): Promise<AiRun> {
  return apiRequest(`/api/v1/ai-runs/${encodeURIComponent(runId)}/decision`, {
    method: 'POST',
    body: JSON.stringify({
      decision,
      note: note.trim() || null,
      modified_result: modifiedResult,
    }),
  }, token)
}
