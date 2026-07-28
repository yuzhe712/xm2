import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { App } from './App'

vi.mock('./hooks/useAuth', () => ({
  useAuth: () => ({
    auth: { token: 'test-token', user: { token: 't', user_id: 'zhangsan', name: '张三', role: 'operator' } },
    authHeaders: { Authorization: 'Bearer test-token' },
    user: { token: 't', user_id: 'zhangsan', name: '张三', role: 'operator' },
    loading: false,
    error: null,
    login: vi.fn(),
    logout: vi.fn(),
    isLoggedIn: true,
    isOperator: true,
    isEmployee: false,
  }),
}))

function mockDeskBackend(): void {
  const emptyHistory = { items: [], limit: 100, offset: 0, total: 0 }
  const catalogItems = {
    ops: [
      {
        evidence_id: 'ev_catalog_payment_alert_001',
        source_type: 'service_catalog',
        source_id: 'CAT-PAYMENT-ALERT',
        source_name: 'mock service catalog',
        retrieved_at: '2026-07-14T10:16:00+08:00',
        desk_scope: 'ops',
        id: 'payment-alert',
        title: '支付服务告警',
        category: '运维告警',
        priority_hint: 'P1',
        affected_service: 'payment-service',
        description: '支付超时、订单量下降、链路延迟等高优先级告警。',
        template_text: '线上支付服务出现超时告警，订单量从正常1000/min降到300/min',
        quality: 'fresh',
        data_mode: 'mock',
        summary: '支付服务告警模板。',
      },
    ],
    support: [
      {
        evidence_id: 'ev_catalog_network_access_001',
        source_type: 'service_catalog',
        source_id: 'CAT-NETWORK-ACCESS',
        source_name: 'mock service catalog',
        retrieved_at: '2026-07-14T10:16:00+08:00',
        desk_scope: 'support',
        id: 'network-access',
        title: '网络访问问题',
        category: '网络',
        priority_hint: 'P2/P3',
        affected_service: 'internal-servicedesk',
        description: '办公网、内网系统、跨区域访问或连接超时问题。',
        template_text: '办公网访问内部工单系统间歇性失败，部分用户反馈连接超时',
        quality: 'fresh',
        data_mode: 'mock',
        summary: '内部网络访问支持模板。',
      },
      {
        evidence_id: 'ev_catalog_account_permission_001',
        source_type: 'service_catalog',
        source_id: 'CAT-ACCOUNT-PERMISSION',
        source_name: 'mock service catalog',
        retrieved_at: '2026-07-14T10:16:00+08:00',
        desk_scope: 'support',
        id: 'account-permission',
        title: '账号权限问题',
        category: '内部支持',
        priority_hint: 'P3',
        affected_service: 'monitoring-console',
        description: '账号开通、权限缺失、只读访问或角色配置问题。',
        template_text: '新入职运维同事无法访问支付服务只读监控面板，需要排查权限配置',
        quality: 'fresh',
        data_mode: 'mock',
        summary: '内部账号权限支持模板。',
      },
    ],
  }
  const supportProcessResponse = {
    ticket_id: 'TCK-20260715-SUPPORT1',
    run_id: 'RUN-20260715-SUPPORT1',
    data_mode: 'mock',
    classification: {
      category: 'support_request',
      summary: '办公网访问内部工单系统间歇性失败',
      affected_service: 'internal-servicedesk',
      symptoms: ['network_access_issue'],
      priority: 'P3',
      priority_reason: '内部支持请求默认按 P3 处理。',
      extracted_metrics: {},
      evidence_ids: ['ev_kb_support_network_001'],
    },
    context: {
      service: null,
      metrics: [],
      deployments: [],
      historical_incidents: [],
      sop_documents: [],
      unknowns: [],
    },
    diagnosis: {
      candidate_root_causes: [],
      unknowns: [],
      abstentions: ['support desk 使用知识库回复建议流程，不生成运维根因诊断。'],
    },
    routing: {
      recommended_team: '内部支持服务台',
      recommended_actions: [
        { action: '确认用户所在办公网络和访问目标系统', evidence_ids: ['ev_kb_support_network_001'] },
      ],
      escalation: '若影响多人则升级给内部支持负责人复核。',
      sop_refs: ['KB-SUPPORT-NETWORK-ACCESS'],
    },
    report: {
      title: '内部支持回复建议：网络访问问题处理说明',
      summary: '已基于 support 服务台知识库生成回复建议。',
      facts: ['用户请求：办公网访问内部工单系统间歇性失败'],
      derived_findings: ['建议由内部支持服务台处理，优先级 P3。'],
      assumptions: ['当前结果来自本地 mock 知识库。'],
      unknowns: [],
      recommendations: ['确认用户所在办公网络和访问目标系统'],
    },
    agent_trace: [
      { step: 'support_intake', status: 'completed', started_at: 'now', completed_at: 'now', summary: 'support intake 完成支持类请求识别', evidence_ids: [] },
      { step: 'support_kb_retrieval', status: 'completed', started_at: 'now', completed_at: 'now', summary: 'support kb retrieval 完成知识库检索', evidence_ids: ['ev_kb_support_network_001'] },
      { step: 'support_routing', status: 'completed', started_at: 'now', completed_at: 'now', summary: 'support routing 完成内部支持分派', evidence_ids: ['ev_kb_support_network_001'] },
      { step: 'support_reply_suggestion', status: 'completed', started_at: 'now', completed_at: 'now', summary: 'support reply suggestion 生成回复建议', evidence_ids: ['ev_kb_support_network_001'] },
    ],
    support_result: {
      request_type: 'internal_support_request',
      matched_articles: ['KB-SUPPORT-NETWORK-ACCESS'],
      reply_suggestions: ['确认用户所在办公网络和访问目标系统'],
      recommended_team: '内部支持服务台',
      escalation: '若影响多人则升级给内部支持负责人复核。',
      evidence_ids: ['ev_kb_support_network_001'],
    },
    evidence: [
      {
        evidence_id: 'ev_kb_support_network_001',
        source_type: 'knowledge_article',
        source_id: 'KB-SUPPORT-NETWORK-ACCESS',
        source_name: 'mock support knowledge base',
        retrieved_at: '2026-07-14T10:16:00+08:00',
        service: 'internal-servicedesk',
        quality: 'fresh',
        data_mode: 'mock',
        summary: '办公网或 VPN 访问内部系统异常时的标准处理步骤。',
      },
    ],
  }
  const knowledgeItems = {
    ops: [
      {
        evidence_id: 'ev_kb_payment_timeout_001',
        source_type: 'sop_document',
        source_id: 'SOP-PAYMENT-TIMEOUT',
        source_name: 'mock support knowledge base',
        retrieved_at: '2026-07-14T10:16:00+08:00',
        desk_scope: 'ops',
        service: 'payment-service',
        article_id: 'SOP-PAYMENT-TIMEOUT',
        title: '支付服务超时处理 SOP',
        actions: ['检查 payment-service 最近 30 分钟部署记录'],
        quality: 'fresh',
        data_mode: 'mock',
        summary: '支付服务超时告警的标准处理步骤。',
      },
      {
        evidence_id: 'ev_kb_db_pool_001',
        source_type: 'sop_document',
        source_id: 'SOP-DB-POOL-EXHAUSTION',
        source_name: 'mock support knowledge base',
        retrieved_at: '2026-07-14T10:16:00+08:00',
        desk_scope: 'ops',
        service: 'payment-service',
        article_id: 'SOP-DB-POOL-EXHAUSTION',
        title: '数据库连接池耗尽处理 SOP',
        actions: ['临时扩容 payment-db 连接池'],
        quality: 'fresh',
        data_mode: 'mock',
        summary: '数据库连接池耗尽的排查与缓解步骤。',
      },
    ],
    support: [
      {
        evidence_id: 'ev_kb_support_network_001',
        source_type: 'knowledge_article',
        source_id: 'KB-SUPPORT-NETWORK-ACCESS',
        source_name: 'mock support knowledge base',
        retrieved_at: '2026-07-14T10:16:00+08:00',
        desk_scope: 'support',
        service: 'internal-servicedesk',
        article_id: 'KB-SUPPORT-NETWORK-ACCESS',
        title: '网络访问问题处理说明',
        actions: ['确认用户所在办公网络和访问目标系统'],
        quality: 'fresh',
        data_mode: 'mock',
        summary: '办公网或 VPN 访问内部系统异常时的标准处理步骤。',
      },
    ],
  }

  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation((input: string, init?: RequestInit) => {
      const url = new URL(input)
      let payload: unknown = emptyHistory
      if (url.pathname.endsWith('/api/v1/tickets/process')) {
        payload = supportProcessResponse
      } else if (url.pathname.endsWith('/support-reply-draft')) {
        const body = JSON.parse(String(init?.body ?? '{}'))
        payload = {
          ticket_id: supportProcessResponse.ticket_id,
          desk_id: 'support',
          input_text: '办公网访问内部工单系统间歇性失败，部分用户反馈连接超时',
          data_mode: 'mock',
          ticket_status: 'resolved',
          created_at: 'now',
          updated_at: 'now',
          support_reply_draft: {
            draft_id: 'DRF-001',
            ticket_id: supportProcessResponse.ticket_id,
            run_id: supportProcessResponse.run_id,
            source: 'human_edited_from_deterministic_suggestion',
            reply_text: body.reply_text,
            report_summary: body.report_summary,
            evidence_ids: body.evidence_ids,
            status: body.status,
            editor: body.editor,
            created_at: 'now',
            updated_at: 'now',
            approved_at: body.status === 'approved' || body.status === 'sent' ? 'now' : null,
            sent_at: body.status === 'sent' ? 'now' : null,
          },
          latest_run: {
            run_id: supportProcessResponse.run_id,
            status: 'completed',
            data_mode: 'mock',
            route_mode: 'deterministic',
            started_at: 'now',
            completed_at: 'now',
            response: supportProcessResponse,
            error: null,
            agent_runs: [],
            supervisor_decisions: [],
            evidence: supportProcessResponse.evidence,
          },
        }
      } else if (url.pathname.endsWith('/api/v1/desks/ops/catalog')) {
        payload = { desk_id: 'ops', data_mode: 'mock', items: catalogItems.ops }
      } else if (url.pathname.endsWith('/api/v1/desks/support/catalog')) {
        payload = { desk_id: 'support', data_mode: 'mock', items: catalogItems.support }
      } else if (url.pathname.endsWith('/api/v1/desks/ops/knowledge')) {
        payload = { desk_id: 'ops', data_mode: 'mock', items: knowledgeItems.ops }
      } else if (url.pathname.endsWith('/api/v1/desks/support/knowledge')) {
        payload = { desk_id: 'support', data_mode: 'mock', items: knowledgeItems.support }
      }
      return Promise.resolve(
        new Response(JSON.stringify(payload), {
          status: 200,
          headers: { 'content-type': 'application/json' },
        }),
      )
    }),
  )
}

function enterOpsDesk(): void {
  fireEvent.click(screen.getByRole('button', { name: /IT 运维服务台/ }))
}

function enterSupportDesk(): void {
  fireEvent.click(screen.getByRole('button', { name: /内部支持服务台/ }))
}

describe('App ServiceDesk navigation', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.unstubAllGlobals()
    mockDeskBackend()
  })

  it('shows the service portal desk choices by default', async () => {
    render(<App />)

    expect(screen.queryByText('IntelliTicket 服务台')).not.toBeInTheDocument()
    expect(screen.queryByRole('navigation', { name: '模块导航' })).not.toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '选择您要报告问题的服务台' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /IT Helpdesk \/ IT 运维服务台/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /基础设施 \/ 内部支持服务台/ })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /人事行政服务台/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /智能工单处理台/ })).not.toBeInTheDocument()
    expect(screen.queryByText('历史工单')).not.toBeInTheDocument()

    await waitFor(() => expect(fetch).toHaveBeenCalled())
  })

  it('opens the operations desk with its own request-focused navigation', async () => {
    render(<App />)
    enterOpsDesk()

    expect(screen.getByText('IT Helpdesk / IT 运维服务台')).toBeInTheDocument()
    expect(screen.queryByText('处理生产系统告警、服务故障、性能异常和变更影响。')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '事件管理' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '问题管理' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '变更管理' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: '智能处理' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '请求' })).toHaveAttribute('aria-current', 'page')
    expect(screen.getByLabelText('搜索请求')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '未解决' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '新建请求' })).toBeInTheDocument()
    await waitFor(() =>
      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining('desk_id=ops'),
        expect.objectContaining({
          headers: expect.objectContaining({ Authorization: 'Bearer test-token' }),
        }),
      ),
    )
  })

  it('opens support desk with support-only catalog as service scope reference', async () => {
    render(<App />)
    enterSupportDesk()

    expect(screen.getByText('基础设施 / 内部支持服务台')).toBeInTheDocument()
    expect(screen.queryByText('处理员工账号、权限申请、VPN、办公网和内部系统访问问题。')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '回复草稿' })).not.toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '内部支持服务目录' })).toBeInTheDocument()
    await waitFor(() =>
      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining('desk_id=support'),
        expect.objectContaining({
          headers: expect.objectContaining({ Authorization: 'Bearer test-token' }),
        }),
      ),
    )
    expect(await screen.findByText('网络访问问题')).toBeInTheDocument()
    expect(screen.getByText('账号权限问题')).toBeInTheDocument()
    expect(screen.queryByText('支付服务告警')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '使用模板' })).not.toBeInTheDocument()
    expect(screen.getByText(/查看当前服务台覆盖的问题类型和处理范围/)).toBeInTheDocument()
  })

  it('renders support reply suggestion instead of ops diagnosis after support processing', async () => {
    render(<App />)
    enterSupportDesk()

    fireEvent.click(screen.getByRole('button', { name: '智能处理' }))
    fireEvent.change(screen.getByLabelText('工单内容'), {
      target: { value: '办公网访问内部工单系统间歇性失败，部分用户反馈连接超时' },
    })
    fireEvent.click(screen.getByRole('button', { name: '同步处理 / REST' }))

    expect(await screen.findByRole('heading', { name: '内部支持回复草稿' })).toBeInTheDocument()
    expect(screen.getByText('内部支持回复建议：网络访问问题处理说明')).toBeInTheDocument()
    expect(screen.getAllByText('确认用户所在办公网络和访问目标系统').length).toBeGreaterThan(0)
    expect(screen.getByText('support_reply_suggestion')).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: '诊断' })).not.toBeInTheDocument()
  })

  it('saves support reply draft from the AI workspace', async () => {
    render(<App />)
    enterSupportDesk()

    fireEvent.click(screen.getByRole('button', { name: '智能处理' }))
    fireEvent.change(screen.getByLabelText('工单内容'), {
      target: { value: '办公网访问内部工单系统间歇性失败，部分用户反馈连接超时' },
    })
    fireEvent.click(screen.getByRole('button', { name: '同步处理 / REST' }))
    const editor = await screen.findByLabelText('可编辑回复')
    fireEvent.change(editor, { target: { value: '请补充当前办公网络和访问目标系统。' } })
    fireEvent.click(screen.getByRole('button', { name: '保存草稿' }))

    await waitFor(() => {
      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/tickets/TCK-20260715-SUPPORT1/support-reply-draft'),
        expect.objectContaining({ method: 'PATCH' }),
      )
    })
    expect(await screen.findByText('human_edited_from_deterministic_suggestion')).toBeInTheDocument()
  })

  it('reopens a cancelled ticket lifecycle and sends it back to processing with original text', async () => {
    const cancelledDetail = {
      ticket_id: 'TCK-20260717-CANCEL01',
      desk_id: 'support',
      input_text: '办公网访问内部工单系统间歇性失败，部分用户反馈连接超时',
      data_mode: 'mock',
      ticket_status: 'cancelled',
      assigned_team: null,
      resolution_summary: null,
      closed_at: null,
      created_at: 'now',
      updated_at: 'now',
      support_reply_draft: null,
      latest_run: {
        run_id: 'RUN-20260717-CANCEL01',
        status: 'cancelled',
        data_mode: 'mock',
        route_mode: 'deterministic',
        started_at: 'now',
        completed_at: 'now',
        response: null,
        error: { code: 'PROCESSING_CANCELLED', message: '已取消', details: {} },
        agent_runs: [],
        supervisor_decisions: [],
        evidence: [],
      },
    }
    const reopenedDetail = { ...cancelledDetail, ticket_status: 'open', updated_at: 'later' }
    const reprocessResultBase = {
      ticket_id: cancelledDetail.ticket_id,
      run_id: 'RUN-20260717-PREVIEW1',
      data_mode: 'mock',
      classification: {
        category: 'support_request',
        summary: cancelledDetail.input_text,
        affected_service: 'internal-servicedesk',
        symptoms: ['network_access_issue'],
        priority: 'P3',
        priority_reason: '内部支持请求默认按 P3 处理。',
        extracted_metrics: {},
        evidence_ids: ['ev_kb_support_network_001'],
      },
      context: {
        service: null,
        metrics: [],
        deployments: [],
        historical_incidents: [],
        sop_documents: [],
        unknowns: [],
      },
      diagnosis: { candidate_root_causes: [], unknowns: [], abstentions: [] },
      routing: {
        recommended_team: '内部支持服务台',
        recommended_actions: [
          { action: '确认用户所在办公网络和访问目标系统', evidence_ids: ['ev_kb_support_network_001'] },
        ],
        escalation: '若影响多人则升级给内部支持负责人复核。',
        sop_refs: ['KB-SUPPORT-NETWORK-ACCESS'],
      },
      report: {
        title: '内部支持回复建议：网络访问问题处理说明',
        summary: '已基于 support 服务台知识库生成回复建议。',
        facts: [],
        derived_findings: [],
        assumptions: [],
        unknowns: [],
        recommendations: ['确认用户所在办公网络和访问目标系统'],
      },
      agent_trace: [
        { step: 'support_reply_suggestion', status: 'completed', started_at: 'later', completed_at: 'later', summary: 'support reply suggestion 生成回复建议', evidence_ids: ['ev_kb_support_network_001'] },
      ],
      support_result: {
        request_type: 'internal_support_request',
        matched_articles: ['KB-SUPPORT-NETWORK-ACCESS'],
        reply_suggestions: ['确认用户所在办公网络和访问目标系统'],
        recommended_team: '内部支持服务台',
        escalation: '若影响多人则升级给内部支持负责人复核。',
        evidence_ids: ['ev_kb_support_network_001'],
      },
      evidence: [
        {
          evidence_id: 'ev_kb_support_network_001',
          source_type: 'knowledge_article',
          source_id: 'KB-SUPPORT-NETWORK-ACCESS',
          source_name: 'mock support knowledge base',
          quality: 'fresh',
          data_mode: 'mock',
          summary: '办公网或 VPN 访问内部系统异常时的标准处理步骤。',
        },
      ],
    }
    const previewResponse = reprocessResultBase
    const reprocessedResponse = { ...reprocessResultBase, run_id: 'RUN-20260717-REPROC1' }
    const reprocessedDetail = {
      ...reopenedDetail,
      latest_run: {
        run_id: reprocessedResponse.run_id,
        status: 'completed',
        data_mode: 'mock',
        route_mode: 'deterministic',
        started_at: 'later',
        completed_at: 'later',
        response: reprocessedResponse,
        error: null,
        agent_runs: [],
        supervisor_decisions: [],
        evidence: reprocessedResponse.evidence,
      },
    }
    const historyList = {
      items: [{
        ticket_id: cancelledDetail.ticket_id,
        desk_id: 'support',
        latest_run_id: cancelledDetail.latest_run.run_id,
        created_at: 'now',
        updated_at: 'now',
        data_mode: 'mock',
        status: 'cancelled',
        ticket_status: 'cancelled',
        summary: cancelledDetail.input_text,
        affected_service: 'internal-servicedesk',
        priority: 'P3',
        report_title: '已取消的支持请求',
      }],
      limit: 100,
      offset: 0,
      total: 1,
    }
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation((input: string, init?: RequestInit) => {
        const url = new URL(input)
        let payload: unknown = { items: [], limit: 100, offset: 0, total: 0 }
        if (url.pathname === '/api/v1/tickets' && url.searchParams.get('desk_id') === 'support') {
          payload = historyList
        } else if (url.pathname.endsWith('/api/v1/tickets/TCK-20260717-CANCEL01/reprocess/preview')) {
          payload = previewResponse
        } else if (url.pathname.endsWith('/api/v1/tickets/TCK-20260717-CANCEL01/reprocess')) {
          payload = reprocessedDetail
        } else if (url.pathname.endsWith('/api/v1/tickets/TCK-20260717-CANCEL01') && init?.method === 'PATCH') {
          payload = reopenedDetail
        } else if (url.pathname.endsWith('/api/v1/tickets/TCK-20260717-CANCEL01')) {
          payload = cancelledDetail
        } else if (url.pathname.endsWith('/api/v1/desks/support/catalog')) {
          payload = { desk_id: 'support', data_mode: 'mock', items: [] }
        } else if (url.pathname.endsWith('/api/v1/desks/support/knowledge')) {
          payload = { desk_id: 'support', data_mode: 'mock', items: [] }
        }
        return Promise.resolve(new Response(JSON.stringify(payload), {
          status: 200,
          headers: { 'content-type': 'application/json' },
        }))
      }),
    )

    render(<App />)
    enterSupportDesk()
    fireEvent.click(screen.getByRole('button', { name: '请求' }))
    fireEvent.click(await screen.findByRole('button', { name: '查看' }))

    expect(await screen.findByText('最新运行：已取消')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '更多操作' }))
    fireEvent.click(screen.getByRole('button', { name: '重新打开' }))

    await waitFor(() => {
      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/tickets/TCK-20260717-CANCEL01'),
        expect.objectContaining({ method: 'PATCH' }),
      )
    })
    expect(await screen.findByText('待处理')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '重新处理此工单' }))

    expect(screen.getByRole('button', { name: '智能处理' })).toHaveAttribute('aria-current', 'page')
    expect(screen.getByLabelText('工单内容')).toHaveValue(cancelledDetail.input_text)
    expect(screen.getByText(/当前正在预览重新处理 TCK-20260717-CANCEL01/)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '同步处理 / REST' }))
    await waitFor(() => {
      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/tickets/TCK-20260717-CANCEL01/reprocess/preview'),
        expect.objectContaining({ method: 'POST' }),
      )
    })
    expect(await screen.findByRole('heading', { name: '内部支持回复草稿' })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '保存到原工单' }))
    await waitFor(() => {
      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/tickets/TCK-20260717-CANCEL01/reprocess'),
        expect.objectContaining({ method: 'POST' }),
      )
    })
    expect(await screen.findByText('最新运行：已完成')).toBeInTheDocument()
    expect(screen.getAllByText('RUN-20260717-REPROC1').length).toBeGreaterThan(0)
  })

  it('does not expose removed placeholder modules', () => {
    render(<App />)
    enterOpsDesk()

    expect(screen.queryByRole('button', { name: '事件管理' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '问题管理' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '变更管理' })).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '返回门户' }))
    enterSupportDesk()
    expect(screen.queryByRole('button', { name: '回复草稿' })).not.toBeInTheDocument()
  })

  it('renders desk-scoped knowledge base content inside the operations desk', async () => {
    render(<App />)
    enterOpsDesk()

    fireEvent.click(screen.getByRole('button', { name: '知识库' }))

    expect(screen.getByRole('heading', { name: '知识库 / SOP' })).toBeInTheDocument()
    expect(await screen.findByText('支付服务超时处理 SOP')).toBeInTheDocument()
    expect(screen.getByText('数据库连接池耗尽处理 SOP')).toBeInTheDocument()
    expect(screen.queryByText('网络访问问题处理说明')).not.toBeInTheDocument()
    expect(screen.queryByText('知识库模块暂未实现')).not.toBeInTheDocument()
  })

  it('renders support-scoped knowledge base content inside the support desk', async () => {
    render(<App />)
    enterSupportDesk()

    fireEvent.click(screen.getByRole('button', { name: '知识库' }))

    expect(await screen.findByText('网络访问问题处理说明')).toBeInTheDocument()
    expect(screen.queryByText('支付服务超时处理 SOP')).not.toBeInTheDocument()
  })

  it('renders report stat tiles based on loaded history', () => {
    render(<App />)
    enterOpsDesk()

    fireEvent.click(screen.getByRole('button', { name: '报表' }))

    expect(screen.getByRole('heading', { name: '报表' })).toBeInTheDocument()
    expect(screen.getByText('总工单数')).toBeInTheDocument()
    expect(screen.getByText('失败 / 未解决')).toBeInTheDocument()
    expect(screen.getByText('当前详情证据数')).toBeInTheDocument()
    expect(screen.getByText('最近处理记录')).toBeInTheDocument()
  })

  it('keeps settings available in the app shell', async () => {
    render(<App />)
    enterOpsDesk()

    fireEvent.click(screen.getByRole('button', { name: '设置' }))

    expect(screen.getByText('实例设置')).toBeInTheDocument()
    expect(screen.getByText('后端连接')).toBeInTheDocument()

    await waitFor(() => expect(fetch).toHaveBeenCalled())
  })
})
