import { authLoginUrl } from '../config/backend'
import type { LoginRequest, LoginResponse } from '../types/tickets'

export interface ApiErrorPayload {
  error: { code: string; message: string; details: Record<string, unknown> }
}

export class ApiError extends Error {
  code: string
  constructor(code: string, message: string) {
    super(message)
    this.code = code
  }
}

export async function login(
  request: LoginRequest,
  fetcher: typeof fetch = fetch,
  baseUrl?: string,
): Promise<LoginResponse> {
  const response = await fetcher(authLoginUrl(baseUrl), {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(request),
  })
  const payload = await response.json()
  if (!response.ok) {
    const ep = payload as ApiErrorPayload
    if (ep.error) {
      throw new ApiError(ep.error.code, ep.error.message)
    }
    throw new ApiError('HTTP_ERROR', `请求失败：${response.status}`)
  }
  return payload as LoginResponse
}
