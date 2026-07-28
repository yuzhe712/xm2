import { apiBaseUrl, normalizeApiBaseUrl } from '../config/backend'

interface ErrorPayload {
  error?: {
    code?: string
    message?: string
    details?: Record<string, unknown>
  }
}

export class ApiClientError extends Error {
  constructor(
    public readonly code: string,
    message: string,
    public readonly status: number,
    public readonly details: Record<string, unknown> = {},
  ) {
    super(message)
    this.name = 'ApiClientError'
  }
}

export async function apiRequest<T>(
  path: string,
  options: RequestInit = {},
  token?: string,
  fetcher: typeof fetch = fetch,
  baseUrl = apiBaseUrl,
): Promise<T> {
  const headers = new Headers(options.headers)
  if (options.body && !headers.has('content-type')) headers.set('content-type', 'application/json')
  if (token) headers.set('authorization', `Bearer ${token}`)
  const response = await fetcher(`${normalizeApiBaseUrl(baseUrl)}${path}`, { ...options, headers })
  const payload = (await response.json().catch(() => ({}))) as T & ErrorPayload
  if (!response.ok) {
    throw new ApiClientError(
      payload.error?.code ?? 'HTTP_ERROR',
      payload.error?.message ?? `请求失败：${response.status}`,
      response.status,
      payload.error?.details,
    )
  }
  return payload
}
