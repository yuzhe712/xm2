import { FormEvent, useEffect, useState } from 'react'

import { useAuth } from '../../app/AuthProvider'
import { createUser, listTeams, listUsers, updateUser } from '../../api/admin'
import type { SessionUser, Team, UserRole } from '../../types/workflow'

export function AdminUsersPage(): JSX.Element {
  const auth = useAuth()
  const [users, setUsers] = useState<SessionUser[]>([])
  const [teams, setTeams] = useState<Team[]>([])
  const [form, setForm] = useState({ username: '', display_name: '', role: 'employee' as UserRole, password: '', team_id: '' })
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const load = async () => {
    if (!auth.token) return
    try { const [nextUsers, nextTeams] = await Promise.all([listUsers(auth.token), listTeams(auth.token)]); setUsers(nextUsers); setTeams(nextTeams) }
    catch (caught) { setError(caught instanceof Error ? caught.message : '加载失败') }
  }
  useEffect(() => { void load() }, [auth.token])

  const submit = async (event: FormEvent) => {
    event.preventDefault(); if (!auth.token) return
    setBusy(true); setError(null)
    try { await createUser({ ...form, team_id: form.team_id || null }, auth.token); setForm({ username: '', display_name: '', role: 'employee', password: '', team_id: '' }); await load() }
    catch (caught) { setError(caught instanceof Error ? caught.message : '创建失败') }
    finally { setBusy(false) }
  }

  const toggle = async (user: SessionUser) => {
    if (!auth.token) return
    setBusy(true)
    try { await updateUser(user.id, { is_active: !user.is_active }, auth.token); await load() }
    catch (caught) { setError(caught instanceof Error ? caught.message : '更新失败') }
    finally { setBusy(false) }
  }

  return <div className="page-stack"><header className="page-header"><div><span className="eyebrow">管理控制台</span><h1>用户</h1><p>创建账号、分配角色和停用访问权限。</p></div><div className="page-stat"><strong>{users.filter((user) => user.is_active).length}</strong><span>启用账号</span></div></header>{error && <div className="error-banner" role="alert">{error}</div>}
    <form className="surface inline-create-form" autoComplete="off" onSubmit={submit}><h2>创建用户</h2><div className="form-grid admin-form-grid"><label><span>用户名</span><input aria-label="新用户用户名" autoComplete="off" value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} /></label><label><span>显示名称</span><input aria-label="新用户显示名称" autoComplete="off" value={form.display_name} onChange={(e) => setForm({ ...form, display_name: e.target.value })} /></label><label><span>角色</span><select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value as UserRole })}><option value="employee">员工</option><option value="operator">运维</option><option value="admin">管理员</option></select></label><label><span>团队</span><select value={form.team_id} onChange={(e) => setForm({ ...form, team_id: e.target.value })}><option value="">未分配</option>{teams.filter((team) => team.is_active).map((team) => <option key={team.id} value={team.id}>{team.name}</option>)}</select></label><label><span>初始密码</span><input aria-label="新用户初始密码" autoComplete="new-password" type="password" minLength={12} value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} /></label><button type="submit" disabled={busy || !form.username || !form.display_name || form.password.length < 12}>创建</button></div></form>
    <section className="data-table" aria-label="用户列表"><div className="data-row data-head"><span>用户</span><span>角色</span><span>团队</span><span>状态</span><span>操作</span></div>{users.map((user) => <div className="data-row" key={user.id}><span><strong>{user.display_name}</strong><small>{user.username}</small></span><span>{user.role}</span><span>{teams.find((team) => team.id === user.team_id)?.name ?? '未分配'}</span><span><span className={user.is_active ? 'state-active' : 'state-inactive'}>{user.is_active ? '启用' : '停用'}</span></span><span><button className="button-quiet" type="button" disabled={busy || user.id === auth.user?.id} onClick={() => void toggle(user)}>{user.is_active ? '停用' : '启用'}</button></span></div>)}</section></div>
}
