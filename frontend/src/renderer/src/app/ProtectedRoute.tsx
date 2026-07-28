import { Navigate, Outlet, useLocation } from 'react-router-dom'

import { useAuth } from './AuthProvider'
import type { UserRole } from '../types/workflow'

export const ROLE_HOME: Record<UserRole, string> = {
  employee: '/employee/tickets',
  operator: '/operator/queue',
  admin: '/admin/users',
}

export function ProtectedRoute({ roles }: { roles: UserRole[] }): JSX.Element {
  const auth = useAuth()
  const location = useLocation()

  if (auth.loading) return <div className="route-loading">正在验证登录状态...</div>
  if (!auth.user || !auth.token) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />
  }
  if (!roles.includes(auth.user.role)) return <Navigate to={ROLE_HOME[auth.user.role]} replace />
  return <Outlet />
}
