import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { App } from './App'
import type { SessionUser, UserRole } from './types/workflow'

const users: Record<UserRole, SessionUser> = {
  employee: { id: 'employee-id', username: 'wangwu', display_name: '王五', role: 'employee', team_id: null, is_active: true },
  operator: { id: 'operator-id', username: 'zhangsan', display_name: '张三', role: 'operator', team_id: 'team-1', is_active: true },
  admin: { id: 'admin-id', username: 'testadmin', display_name: '测试管理员', role: 'admin', team_id: null, is_active: true },
}

const summary = {
  ticket_id: 'TCK-20260728-ABCDEF12', desk_id: 'ops', latest_run_id: 'RUN-20260728-ABCDEF12',
  created_at: '2026-07-28T09:00:00+08:00', updated_at: '2026-07-28T09:10:00+08:00',
  data_mode: 'real', status: 'failed', ticket_status: 'pending', submitter: 'wangwu',
  summary: '无法访问内部系统', affected_service: 'internal-portal', priority: 'P2', version: 1,
  assignee_id: null, resolution_due_at: '2026-07-28T17:00:00+08:00',
}

const workflow = {
  ticket_id: summary.ticket_id, title: summary.summary, description: '登录后持续提示没有访问权限。',
  desk_id: 'ops', data_mode: 'real', status: 'pending', priority: 'P2', category: 'access',
  submitter_id: users.employee.id, submitter: users.employee.username, assigned_team_id: null,
  assigned_team: null, assignee_id: null, claimed_by: null, resolution_summary: null, root_cause: null,
  fix_action: null, verification: null, response_due_at: '2026-07-28T09:30:00+08:00',
  resolution_due_at: summary.resolution_due_at, first_responded_at: null, resolved_at: null, closed_at: null,
  version: 1, created_at: summary.created_at, updated_at: summary.updated_at,
}

let activeRole: UserRole = 'employee'

function response(payload: unknown, status = 200): Promise<Response> {
  return Promise.resolve(new Response(JSON.stringify(payload), { status, headers: { 'content-type': 'application/json' } }))
}

function installBackend(role: UserRole): void {
  activeRole = role
  vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input))
    const path = url.pathname
    if (path === '/api/v1/auth/login') return response({ token: 'test-token', user_id: users[activeRole].username, name: users[activeRole].display_name, role: activeRole })
    if (path === '/api/v1/users/me') return response(users[activeRole])
    if (path === '/api/v1/tickets/mine') return response({ items: [summary], limit: 100, offset: 0, total: 1 })
    if (path === '/api/v1/tickets/queue') return response({ items: [summary], limit: 100, offset: 0, total: 1 })
    if (path === '/api/v1/tickets') return response({ items: [{ ...summary, ticket_status: 'in_progress', assignee_id: users.operator.id }], limit: 100, offset: 0, total: 1 })
    if (path.endsWith('/workflow')) return response(workflow)
    if (path.endsWith('/comments')) {
      if (init?.method === 'POST') return response({ id: 'comment-new', ticket_id: summary.ticket_id, author_id: users[activeRole].id, author: users[activeRole].username, visibility: 'public', body: '正在处理', created_at: summary.updated_at, updated_at: summary.updated_at }, 201)
      const items = [{ id: 'public-1', ticket_id: summary.ticket_id, author_id: users.operator.id, author: 'zhangsan', visibility: 'public', body: '已收到请求', created_at: summary.updated_at, updated_at: summary.updated_at }]
      if (activeRole !== 'employee') items.push({ ...items[0], id: 'internal-1', visibility: 'internal', body: '内部排查记录' })
      return response({ items })
    }
    if (path.endsWith('/timeline')) return response({ items: [{ id: 'event-1', ticket_id: summary.ticket_id, actor_id: users.employee.id, actor: 'wangwu', event_type: 'ticket_created', from_status: null, to_status: 'pending', visibility: 'public', payload: {}, created_at: summary.created_at }] })
    if (path === `/api/v1/tickets/${summary.ticket_id}`) return response({ ticket_id: summary.ticket_id, desk_id: 'ops', input_text: workflow.description, data_mode: 'real', ticket_status: 'pending', created_at: summary.created_at, updated_at: summary.updated_at, latest_run: null, version: 1, ai_run_id: summary.latest_run_id, ai_status: 'failed', ai_result: null })
    if (path === `/api/v1/ai-runs/${summary.latest_run_id}`) return response({ id: summary.latest_run_id, ticket_id: summary.ticket_id, status: 'failed', stage: 'retrieve_diagnose', progress: 45, pipeline_version: 'v2', provider: 'openai-compatible', model: 'test-model', prompt_version: 'p2', result: null, evidence: [], confidence: null, error_code: 'LLM_TIMEOUT', error_message: '模型请求超时', duration_ms: 1000, decision: null, retry_count: 2, created_at: summary.created_at, updated_at: summary.updated_at })
    if (path.endsWith('/claim')) return response({ ...workflow, status: 'in_progress', assignee_id: users.operator.id, claimed_by: users.operator.username, version: 2 })
    if (path.endsWith('/ai-runs') && init?.method === 'POST') return response({ id: 'RUN-20260728-12345678', ticket_id: summary.ticket_id, status: 'queued', stage: 'queued', progress: 0 }, 202)
    if (path === '/api/v1/tickets/submit') return response({ ticket_id: summary.ticket_id, status: 'pending', created_at: summary.created_at, text: workflow.description, desk_id: 'ops', submitter: users.employee.username, version: 1 })
    if (path === '/api/v1/users') return response(Object.values(users))
    if (path === '/api/v1/teams') return response([{ id: 'team-1', code: 'ops', name: 'IT 运维组', is_active: true, created_at: summary.created_at, updated_at: summary.updated_at }])
    if (path === '/api/v1/sla-policies') return response([{ id: 'sla-1', name: 'P2 high', priority: 'P2', response_minutes: 30, resolution_minutes: 480, is_active: true, created_at: summary.created_at, updated_at: summary.updated_at }])
    if (path === '/api/v1/service-catalog') return response([{ id: 'service-1', service_key: 'internal-portal', name: '内部系统', description: '', desk_id: 'ops', team_id: 'team-1', keywords: ['访问'], default_category: 'access', is_active: true, created_at: summary.created_at, updated_at: summary.updated_at }])
    return response({ error: { code: 'NOT_FOUND', message: path, details: {} } }, 404)
  }))
}

function setSession(role: UserRole): void {
  activeRole = role
  localStorage.setItem('intelliticket-auth', JSON.stringify({ token: 'test-token', user: users[role] }))
}

function open(path: string, role?: UserRole): void {
  if (role) setSession(role)
  window.history.replaceState({}, '', path)
  render(<App />)
}

describe('P3 role-based application', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.unstubAllGlobals()
    installBackend('employee')
    window.history.replaceState({}, '', '/login')
  })

  it('shows a credential-only login without demo account hints', () => {
    open('/login')
    expect(screen.getByRole('heading', { name: '登录' })).toBeInTheDocument()
    expect(screen.queryByText(/演示账号|默认密码|企业级/)).not.toBeInTheDocument()
  })

  it('logs an employee into the employee workflow', async () => {
    open('/login')
    fireEvent.change(screen.getByLabelText('用户名'), { target: { value: 'wangwu' } })
    fireEvent.change(screen.getByLabelText('密码'), { target: { value: 'correct-password' } })
    fireEvent.click(screen.getByRole('button', { name: '登录' }))
    expect(await screen.findByRole('heading', { name: '我的工单' })).toBeInTheDocument()
    expect(window.location.pathname).toBe('/employee/tickets')
  })

  it('shows employees only employee navigation', async () => {
    open('/employee/tickets', 'employee')
    const navigation = await screen.findByRole('navigation', { name: '员工门户导航' })
    expect(within(navigation).getByRole('link', { name: /新建工单/ })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /待处理队列|用户/ })).not.toBeInTheDocument()
  })

  it('submits a new employee ticket and opens its stable detail URL', async () => {
    open('/employee/tickets/new', 'employee')
    fireEvent.change(await screen.findByLabelText('工单主题'), { target: { value: '无法访问内部系统' } })
    fireEvent.change(screen.getByLabelText('工单描述'), { target: { value: workflow.description } })
    fireEvent.click(screen.getByRole('button', { name: '提交工单' }))
    expect(await screen.findByRole('heading', { name: summary.summary })).toBeInTheDocument()
    expect(window.location.pathname).toBe(`/employee/tickets/${summary.ticket_id}`)
  })

  it('restores an employee detail page directly from its URL', async () => {
    open(`/employee/tickets/${summary.ticket_id}`, 'employee')
    expect(await screen.findByText(summary.ticket_id)).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: summary.summary })).toBeInTheDocument()
  })

  it('does not render internal comments for employees', async () => {
    open(`/employee/tickets/${summary.ticket_id}`, 'employee')
    expect(await screen.findByText('已收到请求')).toBeInTheDocument()
    expect(screen.queryByText('内部排查记录')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('评论可见范围')).not.toBeInTheDocument()
  })

  it('shows operators only queue and personal work navigation', async () => {
    installBackend('operator')
    open('/operator/queue', 'operator')
    expect(await screen.findByRole('navigation', { name: '运维工作台导航' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /待处理队列/ })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /我的工作/ })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /新建工单|用户/ })).not.toBeInTheDocument()
  })

  it('keeps manual claim and comments available when AI failed', async () => {
    installBackend('operator')
    open(`/operator/tickets/${summary.ticket_id}`, 'operator')
    expect(await screen.findByText('模型请求超时')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /认领工单/ })).toBeEnabled()
    expect(screen.getByLabelText('评论内容')).toBeEnabled()
    expect(screen.getByLabelText('评论可见范围')).toBeInTheDocument()
  })

  it('filters the operator personal work list by assignee', async () => {
    installBackend('operator')
    open('/operator/work', 'operator')
    expect(await screen.findByRole('heading', { name: '我的工作' })).toBeInTheDocument()
    expect(screen.getByText(summary.ticket_id)).toBeInTheDocument()
  })

  it('shows administrator configuration without employee or operator workflows', async () => {
    installBackend('admin')
    open('/admin/users', 'admin')
    expect(await screen.findByRole('heading', { name: '用户' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /团队/ })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /SLA/ })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /服务目录/ })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /我的工单|待处理队列/ })).not.toBeInTheDocument()
  })

  it('redirects a role away from another role workspace', async () => {
    open('/operator/queue', 'employee')
    await waitFor(() => expect(window.location.pathname).toBe('/employee/tickets'))
    expect(await screen.findByRole('heading', { name: '我的工单' })).toBeInTheDocument()
  })
})
