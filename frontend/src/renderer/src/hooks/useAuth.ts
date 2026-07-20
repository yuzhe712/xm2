import { useCallback, useEffect, useState } from 'react'
import { login as apiLogin } from '../api/auth'
import type { LoginRequest, LoginResponse } from '../types/tickets'

const STORAGE_KEY = 'intelliticket-auth'

interface AuthState {
  token: string
  user: LoginResponse
}

function loadAuth(): AuthState | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as AuthState
    if (!parsed.token || !parsed.user) return null
    return parsed
  } catch {
    return null
  }
}

function saveAuth(state: AuthState | null) {
  if (state) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state))
  } else {
    localStorage.removeItem(STORAGE_KEY)
  }
}

export function useAuth() {
  const [auth, setAuth] = useState<AuthState | null>(loadAuth)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const loginAction = useCallback(async (request: LoginRequest) => {
    setLoading(true)
    setError(null)
    try {
      const user = await apiLogin(request)
      const state: AuthState = { token: user.token, user }
      saveAuth(state)
      setAuth(state)
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : '登录失败'
      setError(msg)
      throw e
    } finally {
      setLoading(false)
    }
  }, [])

  const logout = useCallback(() => {
    saveAuth(null)
    setAuth(null)
  }, [])

  useEffect(() => {
    const onStorage = () => setAuth(loadAuth())
    window.addEventListener('storage', onStorage)
    return () => window.removeEventListener('storage', onStorage)
  }, [])

  const authHeaders = auth ? { Authorization: `Bearer ${auth.token}` } : undefined

  return {
    auth,
    authHeaders,
    user: auth?.user ?? null,
    loading,
    error,
    login: loginAction,
    logout,
    isLoggedIn: auth !== null,
    isOperator: auth?.user.role === 'operator',
    isEmployee: auth?.user.role === 'employee',
  }
}
