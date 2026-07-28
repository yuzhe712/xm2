import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'

import { getCurrentUser, login as apiLogin } from '../api/auth'
import type { SessionUser } from '../types/workflow'

const STORAGE_KEY = 'intelliticket-auth'

interface StoredSession {
  token: string
  user: SessionUser
}

interface AuthContextValue {
  token: string | null
  user: SessionUser | null
  loading: boolean
  error: string | null
  login: (username: string, password: string) => Promise<void>
  logout: () => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

function readSession(): StoredSession | null {
  try {
    const parsed = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? 'null') as StoredSession | null
    return parsed?.token && parsed.user?.id ? parsed : null
  } catch {
    return null
  }
}

export function AuthProvider({ children }: { children: React.ReactNode }): JSX.Element {
  const [session, setSession] = useState<StoredSession | null>(readSession)
  const [loading, setLoading] = useState(() => Boolean(readSession()))
  const [error, setError] = useState<string | null>(null)

  const persist = useCallback((next: StoredSession | null) => {
    setSession(next)
    if (next) localStorage.setItem(STORAGE_KEY, JSON.stringify(next))
    else localStorage.removeItem(STORAGE_KEY)
  }, [])

  useEffect(() => {
    if (!session?.token) return
    let active = true
    getCurrentUser(session.token)
      .then((user) => { if (active) persist({ token: session.token, user }) })
      .catch(() => { if (active) persist(null) })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, []) // Validate the restored token once when the application starts.

  const login = useCallback(async (username: string, password: string) => {
    setLoading(true)
    setError(null)
    try {
      const response = await apiLogin({ user_id: username, password })
      const user = await getCurrentUser(response.token)
      persist({ token: response.token, user })
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : '登录失败'
      setError(message)
      throw caught
    } finally {
      setLoading(false)
    }
  }, [persist])

  const logout = useCallback(() => {
    setError(null)
    persist(null)
  }, [persist])

  const value = useMemo<AuthContextValue>(() => ({
    token: session?.token ?? null,
    user: session?.user ?? null,
    loading,
    error,
    login,
    logout,
  }), [error, loading, login, logout, session])

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext)
  if (!value) throw new Error('useAuth 必须在 AuthProvider 中使用')
  return value
}
