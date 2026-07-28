import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'

import { AuthProvider, useAuth } from './app/AuthProvider'
import { ProtectedRoute, ROLE_HOME } from './app/ProtectedRoute'
import { AppShell } from './layouts/AppShell'
import { AdminCatalogPage } from './pages/admin/AdminCatalogPage'
import { AdminSlaPage } from './pages/admin/AdminSlaPage'
import { AdminTeamsPage } from './pages/admin/AdminTeamsPage'
import { AdminUsersPage } from './pages/admin/AdminUsersPage'
import { EmployeeTicketDetailPage } from './pages/employee/EmployeeTicketDetailPage'
import { EmployeeTicketsPage } from './pages/employee/EmployeeTicketsPage'
import { NewTicketPage } from './pages/employee/NewTicketPage'
import { LoginPage } from './pages/LoginPage'
import { OperatorQueuePage } from './pages/operator/OperatorQueuePage'
import { OperatorTicketDetailPage } from './pages/operator/OperatorTicketDetailPage'
import { OperatorWorkPage } from './pages/operator/OperatorWorkPage'

function HomeRedirect(): JSX.Element {
  const auth = useAuth()
  if (auth.loading) return <div className="route-loading">正在加载...</div>
  return <Navigate to={auth.user ? ROLE_HOME[auth.user.role] : '/login'} replace />
}

function AppRoutes(): JSX.Element {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<ProtectedRoute roles={['employee']} />}>
        <Route element={<AppShell role="employee" />}>
          <Route path="/employee/tickets" element={<EmployeeTicketsPage />} />
          <Route path="/employee/tickets/new" element={<NewTicketPage />} />
          <Route path="/employee/tickets/:ticketId" element={<EmployeeTicketDetailPage />} />
        </Route>
      </Route>
      <Route element={<ProtectedRoute roles={['operator']} />}>
        <Route element={<AppShell role="operator" />}>
          <Route path="/operator/queue" element={<OperatorQueuePage />} />
          <Route path="/operator/work" element={<OperatorWorkPage />} />
          <Route path="/operator/tickets/:ticketId" element={<OperatorTicketDetailPage />} />
        </Route>
      </Route>
      <Route element={<ProtectedRoute roles={['admin']} />}>
        <Route element={<AppShell role="admin" />}>
          <Route path="/admin/users" element={<AdminUsersPage />} />
          <Route path="/admin/teams" element={<AdminTeamsPage />} />
          <Route path="/admin/sla" element={<AdminSlaPage />} />
          <Route path="/admin/catalog" element={<AdminCatalogPage />} />
        </Route>
      </Route>
      <Route path="/" element={<HomeRedirect />} />
      <Route path="*" element={<HomeRedirect />} />
    </Routes>
  )
}

export function App(): JSX.Element {
  return <AuthProvider><BrowserRouter><AppRoutes /></BrowserRouter></AuthProvider>
}
