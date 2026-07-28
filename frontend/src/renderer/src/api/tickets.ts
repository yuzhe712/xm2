import {
  authLoginUrl,
  deskCatalogUrl,
  deskKnowledgeUrl,
  myTicketsUrl,
  processTicketUrl,
  processTicketWsUrl,
  supportReplyDraftUrl,
  ticketDetailUrl,
  ticketQueueUrl,
  ticketReprocessPreviewUrl,
  ticketReprocessUrl,
  ticketListUrl,
  ticketSubmitUrl,
  toWebSocketUrl,
} from '../config/backend'
import type {
  ApiErrorPayload,
  CatalogResponse,
  DeskId,
  KnowledgeResponse,
  TicketHistoryDetailResponse,
  TicketHistoryListResponse,
  TicketLifecycleUpdateRequest,
  SupportReplyDraftUpdateRequest,
  TicketProcessRequest,
  TicketProcessResponse,
  TicketSubmitRequest,
  TicketSubmitResponse,
} from '../types/tickets'

function authHeaders(token?: string): Record<string, string> {
  if (!token) return { 'content-type': 'application/json' }
  return {
    'content-type': 'application/json',
    Authorization: `Bearer ${token}`,
  }
}

export class TicketApiError extends Error {
  code: string
  details: Record<string, unknown>

  constructor(code: string, message: string, details: Record<string, unknown> = {}) {
    super(message)
    this.name = 'TicketApiError'
    this.code = code
    this.details = details
  }
}

export async function processTicketRest(
  request: TicketProcessRequest,
  token: string,
  fetcher: typeof fetch = fetch,
  baseUrl?: string,
): Promise<TicketProcessResponse> {
  const response = await fetcher(processTicketUrl(baseUrl), {
    method: 'POST',
    headers: authHeaders(token),
    body: JSON.stringify(request),
  })

  return parseResponse<TicketProcessResponse>(response)
}

async function parseResponse<T>(response: Response): Promise<T> {
  const payload = await response.json()
  if (!response.ok) {
    const errorPayload = payload as ApiErrorPayload
    if (errorPayload.error) {
      throw new TicketApiError(
        errorPayload.error.code,
        errorPayload.error.message,
        errorPayload.error.details,
      )
    }
    throw new TicketApiError('HTTP_ERROR', `请求失败：${response.status}`)
  }
  return payload as T
}

export async function listTickets(
  limit = 20,
  offset = 0,
  token = '',
  fetcher: typeof fetch = fetch,
  baseUrl?: string,
  deskId?: DeskId,
): Promise<TicketHistoryListResponse> {
  const url = new URL(ticketListUrl(baseUrl))
  url.searchParams.set('limit', String(limit))
  url.searchParams.set('offset', String(offset))
  if (deskId) url.searchParams.set('desk_id', deskId)
  const response = await fetcher(url.toString(), { headers: authHeaders(token) })
  return parseResponse<TicketHistoryListResponse>(response)
}

export async function getTicketDetail(
  ticketId: string,
  token: string,
  fetcher: typeof fetch = fetch,
  baseUrl?: string,
): Promise<TicketHistoryDetailResponse> {
  const response = await fetcher(ticketDetailUrl(ticketId, baseUrl), {
    headers: authHeaders(token),
  })
  return parseResponse<TicketHistoryDetailResponse>(response)
}

export async function updateTicketLifecycle(
  ticketId: string,
  request: TicketLifecycleUpdateRequest,
  token: string,
  fetcher: typeof fetch = fetch,
  baseUrl?: string,
): Promise<TicketHistoryDetailResponse> {
  const response = await fetcher(ticketDetailUrl(ticketId, baseUrl), {
    method: 'PATCH',
    headers: authHeaders(token),
    body: JSON.stringify(request),
  })
  return parseResponse<TicketHistoryDetailResponse>(response)
}

export async function updateSupportReplyDraft(
  ticketId: string,
  request: SupportReplyDraftUpdateRequest,
  token: string,
  fetcher: typeof fetch = fetch,
  baseUrl?: string,
): Promise<TicketHistoryDetailResponse> {
  const response = await fetcher(supportReplyDraftUrl(ticketId, baseUrl), {
    method: 'PATCH',
    headers: authHeaders(token),
    body: JSON.stringify(request),
  })
  return parseResponse<TicketHistoryDetailResponse>(response)
}

export async function previewReprocessTicket(
  ticketId: string,
  token: string,
  fetcher: typeof fetch = fetch,
  baseUrl?: string,
): Promise<TicketProcessResponse> {
  const response = await fetcher(ticketReprocessPreviewUrl(ticketId, baseUrl), {
    method: 'POST',
    headers: authHeaders(token),
  })
  return parseResponse<TicketProcessResponse>(response)
}

export async function reprocessTicket(
  ticketId: string,
  token: string,
  fetcher: typeof fetch = fetch,
  baseUrl?: string,
): Promise<TicketHistoryDetailResponse> {
  const response = await fetcher(ticketReprocessUrl(ticketId, baseUrl), {
    method: 'POST',
    headers: authHeaders(token),
  })
  return parseResponse<TicketHistoryDetailResponse>(response)
}

export async function getDeskCatalog(
  deskId: DeskId,
  fetcher: typeof fetch = fetch,
  baseUrl?: string,
): Promise<CatalogResponse> {
  const response = await fetcher(deskCatalogUrl(deskId, baseUrl))
  return parseResponse<CatalogResponse>(response)
}

export async function getDeskKnowledge(
  deskId: DeskId,
  fetcher: typeof fetch = fetch,
  baseUrl?: string,
): Promise<KnowledgeResponse> {
  const response = await fetcher(deskKnowledgeUrl(deskId, baseUrl))
  return parseResponse<KnowledgeResponse>(response)
}

export async function submitTicket(
  request: TicketSubmitRequest,
  token: string,
  fetcher: typeof fetch = fetch,
  baseUrl?: string,
): Promise<TicketSubmitResponse> {
  const response = await fetcher(ticketSubmitUrl(baseUrl), {
    method: 'POST',
    headers: authHeaders(token),
    body: JSON.stringify(request),
  })
  return parseResponse<TicketSubmitResponse>(response)
}

export async function listMyTickets(
  token: string,
  limit = 50,
  offset = 0,
  deskId?: DeskId,
  fetcher: typeof fetch = fetch,
  baseUrl?: string,
): Promise<TicketHistoryListResponse> {
  const url = new URL(myTicketsUrl(baseUrl))
  url.searchParams.set('limit', String(limit))
  url.searchParams.set('offset', String(offset))
  if (deskId) url.searchParams.set('desk_id', deskId)
  const response = await fetcher(url.toString(), { headers: authHeaders(token) })
  return parseResponse<TicketHistoryListResponse>(response)
}

export async function listPendingQueue(
  token: string,
  limit = 50,
  offset = 0,
  fetcher: typeof fetch = fetch,
  baseUrl?: string,
): Promise<TicketHistoryListResponse> {
  const url = new URL(ticketQueueUrl(baseUrl))
  url.searchParams.set('limit', String(limit))
  url.searchParams.set('offset', String(offset))
  const response = await fetcher(url.toString(), { headers: authHeaders(token) })
  return parseResponse<TicketHistoryListResponse>(response)
}




export function createTicketProcessingSocket(token: string, baseUrl?: string): WebSocket {
  const url = new URL(processTicketWsUrl(baseUrl))
  url.searchParams.set('access_token', token)
  return new WebSocket(url.toString())
}

export {
  authLoginUrl,
  processTicketUrl,
  processTicketWsUrl,
  ticketDetailUrl,
  ticketListUrl,
  toWebSocketUrl,
}
