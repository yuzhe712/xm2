import { ClipboardList, Inbox, LogOut, Plus, Settings, ShieldCheck, Users, Wrench } from 'lucide-react'
import { NavLink, Outlet } from 'react-router-dom'

import { useAuth } from '../app/AuthProvider'
import type { UserRole } from '../types/workflow'

const navigation = {
  employee: [
    { to: '/employee/tickets/new', label: '新建工单', icon: Plus },
    { to: '/employee/tickets', label: '我的工单', icon: ClipboardList },
  ],
  operator: [
    { to: '/operator/queue', label: '待处理队列', icon: Inbox },
    { to: '/operator/work', label: '我的工作', icon: Wrench },
  ],
  admin: [
    { to: '/admin/users', label: '用户', icon: Users },
    { to: '/admin/teams', label: '团队', icon: ShieldCheck },
    { to: '/admin/sla', label: 'SLA', icon: ClipboardList },
    { to: '/admin/catalog', label: '服务目录', icon: Settings },
  ],
}

const roleLabels: Record<UserRole, string> = {
  employee: '员工门户',
  operator: '运维工作台',
  admin: '管理控制台',
}

export function AppShell({ role }: { role: UserRole }): JSX.Element {
  const auth = useAuth()
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand-block">
          <span className="brand-mark">IT</span>
          <div><strong>IntelliTicket</strong><span>{roleLabels[role]}</span></div>
        </div>
        <nav aria-label={`${roleLabels[role]}导航`}>
          {navigation[role].map(({ to, label, icon: Icon }) => (
            <NavLink key={to} to={to} className={({ isActive }) => isActive ? 'nav-link active' : 'nav-link'}>
              <Icon aria-hidden="true" size={18} />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="account-block">
          <div><strong>{auth.user?.display_name}</strong><span>{auth.user?.username}</span></div>
          <button className="icon-button" type="button" onClick={auth.logout} aria-label="退出登录" title="退出登录">
            <LogOut aria-hidden="true" size={18} />
          </button>
        </div>
      </aside>
      <main className="workspace"><Outlet /></main>
    </div>
  )
}
