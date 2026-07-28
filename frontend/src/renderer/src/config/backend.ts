export const DEFAULT_API_BASE_URL = 'http://127.0.0.1:8000'

const sameOriginApiBaseUrl =
  typeof window !== 'undefined' && ['http:', 'https:'].includes(window.location.protocol)
    ? window.location.origin
    : DEFAULT_API_BASE_URL

export function normalizeApiBaseUrl(value: string): string {
  return value.trim().replace(/\/$/, '')
}

export const apiBaseUrl = normalizeApiBaseUrl(
  import.meta.env.VITE_INTELLITICKET_API_BASE_URL || sameOriginApiBaseUrl,
)

export function ticketListUrl(baseUrl = apiBaseUrl): string {
  return `${normalizeApiBaseUrl(baseUrl)}/api/v1/tickets`
}

export function authLoginUrl(baseUrl = apiBaseUrl): string {
  return `${normalizeApiBaseUrl(baseUrl)}/api/v1/auth/login`
}

export function ticketSubmitUrl(baseUrl = apiBaseUrl): string {
  return `${normalizeApiBaseUrl(baseUrl)}/api/v1/tickets/submit`
}

export function myTicketsUrl(baseUrl = apiBaseUrl): string {
  return `${normalizeApiBaseUrl(baseUrl)}/api/v1/tickets/mine`
}

export function ticketQueueUrl(baseUrl = apiBaseUrl): string {
  return `${normalizeApiBaseUrl(baseUrl)}/api/v1/tickets/queue`
}


export function deskCatalogUrl(deskId: string, baseUrl = apiBaseUrl): string {
  return `${normalizeApiBaseUrl(baseUrl)}/api/v1/desks/${encodeURIComponent(deskId)}/catalog`
}

export function deskKnowledgeUrl(deskId: string, baseUrl = apiBaseUrl): string {
  return `${normalizeApiBaseUrl(baseUrl)}/api/v1/desks/${encodeURIComponent(deskId)}/knowledge`
}

export function ticketDetailUrl(ticketId: string, baseUrl = apiBaseUrl): string {
  return `${normalizeApiBaseUrl(baseUrl)}/api/v1/tickets/${encodeURIComponent(ticketId)}`
}

export function supportReplyDraftUrl(ticketId: string, baseUrl = apiBaseUrl): string {
  return `${ticketDetailUrl(ticketId, baseUrl)}/support-reply-draft`
}

export function ticketReprocessPreviewUrl(ticketId: string, baseUrl = apiBaseUrl): string {
  return `${ticketDetailUrl(ticketId, baseUrl)}/reprocess/preview`
}

export function ticketReprocessUrl(ticketId: string, baseUrl = apiBaseUrl): string {
  return `${ticketDetailUrl(ticketId, baseUrl)}/reprocess`
}

export function processTicketUrl(baseUrl = apiBaseUrl): string {
  return `${normalizeApiBaseUrl(baseUrl)}/api/v1/tickets/process`
}

export function toWebSocketUrl(httpBaseUrl: string): string {
  const url = new URL(normalizeApiBaseUrl(httpBaseUrl))
  if (url.protocol === 'https:') {
    url.protocol = 'wss:'
  } else {
    url.protocol = 'ws:'
  }
  return normalizeApiBaseUrl(url.toString())
}

export function processTicketWsUrl(baseUrl = apiBaseUrl): string {
  return `${toWebSocketUrl(baseUrl)}/api/v1/tickets/process/ws`
}
