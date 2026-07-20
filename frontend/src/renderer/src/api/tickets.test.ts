import { describe, expect, it, vi } from 'vitest'

import {
  getTicketDetail,
  listTickets,
  previewReprocessTicket,
  processTicketRest,
  processTicketWsUrl,
  reprocessTicket,
  TicketApiError,
  ticketDetailUrl,
  updateSupportReplyDraft,
  updateTicketLifecycle,
  ticketListUrl,
  toWebSocketUrl,
} from './tickets'

const TEST_TOKEN = 'test-token'

const sampleResponse = {
  ticket_id: 'TCK-001',
  run_id: 'RUN-001',
  data_mode: 'mock',
  classification: {},
  context: {},
  diagnosis: {},
  routing: {},
  report: {},
  agent_trace: [],
  evidence: [],
}

describe('tickets api', () => {
  it('maps successful REST responses', async () => {
    const fetcher = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(sampleResponse), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      }),
    )

    const result = await processTicketRest({ text: '测试工单', data_mode: 'mock', desk_id: 'ops' }, TEST_TOKEN, fetcher)

    expect(result.ticket_id).toBe('TCK-001')
    expect(fetcher).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/tickets/process'),
      expect.objectContaining({ method: 'POST' }),
    )
  })

  it('surfaces structured backend errors', async () => {
    const fetcher = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          error: {
            code: 'UNSUPPORTED_DATA_MODE',
            message: '当前仅支持 mock',
            details: { requested_data_mode: 'real' },
          },
        }),
        { status: 400, headers: { 'content-type': 'application/json' } },
      ),
    )

    await expect(processTicketRest({ text: '测试工单', data_mode: 'mock', desk_id: 'ops' }, TEST_TOKEN, fetcher)).rejects.toMatchObject({
      code: 'UNSUPPORTED_DATA_MODE',
      message: '当前仅支持 mock',
    } satisfies Partial<TicketApiError>)
  })

  it('loads ticket history list and detail', async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            items: [
              {
                ticket_id: 'TCK-20260715-ABCDEF12',
                desk_id: 'ops',
                latest_run_id: 'RUN-20260715-1234ABCD',
                created_at: 'now',
                updated_at: 'now',
                data_mode: 'mock',
                status: 'completed',
                ticket_status: 'resolved',
                summary: 'summary',
                affected_service: 'payment-service',
                priority: 'P1',
                report_title: '报告',
              },
            ],
            limit: 20,
            offset: 0,
            total: 1,
          }),
          { status: 200, headers: { 'content-type': 'application/json' } },
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            ticket_id: 'TCK-20260715-ABCDEF12',
            desk_id: 'ops',
            input_text: 'summary',
            data_mode: 'mock',
            ticket_status: 'resolved',
            created_at: 'now',
            updated_at: 'now',
            latest_run: {
              run_id: 'RUN-20260715-1234ABCD',
              status: 'completed',
              data_mode: 'mock',
              route_mode: 'deterministic',
              started_at: 'now',
              completed_at: 'now',
              response: sampleResponse,
              error: null,
              agent_runs: [],
              supervisor_decisions: [],
              evidence: [],
            },
          }),
          { status: 200, headers: { 'content-type': 'application/json' } },
        ),
      )

    const listing = await listTickets(20, 0, fetcher, undefined, 'support')
    const detail = await getTicketDetail('TCK-20260715-ABCDEF12', fetcher)

    expect(fetcher).toHaveBeenCalledWith(expect.stringContaining('desk_id=support'))
    expect(listing.total).toBe(1)
    expect(detail.latest_run!.response?.ticket_id).toBe('TCK-001')
  })

  it('loads failed ticket history detail without a response', async () => {
    const fetcher = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          ticket_id: 'TCK-20260715-ABCDEF12',
          input_text: 'summary',
          data_mode: 'mock',
          created_at: 'now',
          updated_at: 'now',
          latest_run: {
            run_id: 'RUN-20260715-1234ABCD',
            status: 'failed',
            data_mode: 'mock',
            route_mode: 'deterministic',
            started_at: 'now',
            completed_at: 'now',
            response: null,
            error: { code: 'AGENT_TASK_FAILED', message: 'failed', details: {} },
            agent_runs: [
              {
                sequence: 1,
                task_id: 'TASK-1',
                agent_name: 'ticket_intake_agent',
                step: 'ticket_intake',
                status: 'failed',
                route_decision: null,
                observations: ['observed failure'],
                evidence_ids: ['ev_ticket_input_001'],
                error: { code: 'INTAKE_FAILED', message: 'intake failed', details: {} },
                started_at: 'now',
                completed_at: 'now',
              },
            ],
            supervisor_decisions: [],
            evidence: [
              {
                evidence_id: 'ev_ticket_input_001',
                source_type: 'ticket_input',
                source_id: 'TCK-20260715-ABCDEF12',
                source_name: '用户输入工单',
                quality: 'user_provided',
                data_mode: 'mock',
                summary: 'summary',
              },
            ],
          },
        }),
        { status: 200, headers: { 'content-type': 'application/json' } },
      ),
    )

    const detail = await getTicketDetail('TCK-20260715-ABCDEF12', fetcher)

    expect(detail.latest_run!.response).toBeNull()
    expect(detail.latest_run!.error?.code).toBe('AGENT_TASK_FAILED')
    expect(detail.latest_run!.agent_runs[0].observations).toContain('observed failure')
    expect(detail.latest_run!.evidence[0].evidence_id).toBe('ev_ticket_input_001')
  })

  it('updates ticket lifecycle with PATCH', async () => {
    const fetcher = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          ticket_id: 'TCK-20260715-ABCDEF12',
          desk_id: 'ops',
          input_text: 'summary',
          data_mode: 'mock',
          ticket_status: 'closed',
          resolution_summary: '已处理',
          closed_at: 'now',
          created_at: 'now',
          updated_at: 'now',
          latest_run: {
            run_id: 'RUN-20260715-1234ABCD',
            status: 'completed',
            data_mode: 'mock',
            route_mode: 'deterministic',
            started_at: 'now',
            completed_at: 'now',
            response: sampleResponse,
            error: null,
            agent_runs: [],
            supervisor_decisions: [],
            evidence: [],
          },
        }),
        { status: 200, headers: { 'content-type': 'application/json' } },
      ),
    )

    const detail = await updateTicketLifecycle(
      'TCK-20260715-ABCDEF12',
      { ticket_status: 'closed', resolution_summary: '已处理' },
      TEST_TOKEN,
      fetcher,
    )

    expect(fetcher).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/tickets/TCK-20260715-ABCDEF12'),
      expect.objectContaining({ method: 'PATCH' }),
    )
    expect(detail.ticket_status).toBe('closed')
    expect(detail.latest_run!.status).toBe('completed')
  })

  it('previews ticket reprocess with POST without returning detail', async () => {
    const fetcher = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ ...sampleResponse, ticket_id: 'TCK-20260715-ABCDEF12', run_id: 'RUN-20260715-PREVIEW1' }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      }),
    )

    const result = await previewReprocessTicket('TCK-20260715-ABCDEF12', TEST_TOKEN, fetcher)

    expect(fetcher).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/tickets/TCK-20260715-ABCDEF12/reprocess/preview'),
      expect.objectContaining({ method: 'POST' }),
    )
    expect(result.run_id).toBe('RUN-20260715-PREVIEW1')
  })

  it('reprocesses a ticket with POST and returns refreshed detail', async () => {
    const fetcher = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          ticket_id: 'TCK-20260715-ABCDEF12',
          desk_id: 'ops',
          input_text: 'summary',
          data_mode: 'mock',
          ticket_status: 'resolved',
          created_at: 'now',
          updated_at: 'now',
          latest_run: {
            run_id: 'RUN-20260715-REPROC1',
            status: 'completed',
            data_mode: 'mock',
            route_mode: 'deterministic',
            started_at: 'now',
            completed_at: 'now',
            response: { ...sampleResponse, ticket_id: 'TCK-20260715-ABCDEF12', run_id: 'RUN-20260715-REPROC1' },
            error: null,
            agent_runs: [],
            supervisor_decisions: [],
            evidence: [],
          },
        }),
        { status: 200, headers: { 'content-type': 'application/json' } },
      ),
    )

    const detail = await reprocessTicket('TCK-20260715-ABCDEF12', TEST_TOKEN, fetcher)

    expect(fetcher).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/tickets/TCK-20260715-ABCDEF12/reprocess'),
      expect.objectContaining({ method: 'POST' }),
    )
    expect(detail.ticket_id).toBe('TCK-20260715-ABCDEF12')
    expect(detail.latest_run!.run_id).toBe('RUN-20260715-REPROC1')
  })

  it('updates support reply draft with PATCH', async () => {
    const fetcher = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          ticket_id: 'TCK-20260715-ABCDEF12',
          desk_id: 'support',
          input_text: 'summary',
          data_mode: 'mock',
          ticket_status: 'resolved',
          created_at: 'now',
          updated_at: 'now',
          support_reply_draft: {
            draft_id: 'DRF-001',
            ticket_id: 'TCK-20260715-ABCDEF12',
            run_id: 'RUN-20260715-1234ABCD',
            source: 'human_edited_from_deterministic_suggestion',
            reply_text: '请补充所属团队。',
            report_summary: '已编辑摘要',
            evidence_ids: ['ev_kb_support_account_001'],
            status: 'sent',
            editor: 'local-operator',
            created_at: 'now',
            updated_at: 'now',
            approved_at: 'now',
            sent_at: 'now',
          },
          latest_run: {
            run_id: 'RUN-20260715-1234ABCD',
            status: 'completed',
            data_mode: 'mock',
            route_mode: 'deterministic',
            started_at: 'now',
            completed_at: 'now',
            response: sampleResponse,
            error: null,
            agent_runs: [],
            supervisor_decisions: [],
            evidence: [],
          },
        }),
        { status: 200, headers: { 'content-type': 'application/json' } },
      ),
    )

    const detail = await updateSupportReplyDraft(
      'TCK-20260715-ABCDEF12',
      {
        reply_text: '请补充所属团队。',
        report_summary: '已编辑摘要',
        evidence_ids: ['ev_kb_support_account_001'],
        status: 'sent',
      },
      'token-operator',
      fetcher,
    )

    expect(fetcher).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/tickets/TCK-20260715-ABCDEF12/support-reply-draft'),
      expect.objectContaining({
        method: 'PATCH',
        headers: expect.objectContaining({ Authorization: 'Bearer token-operator' }),
      }),
    )
    expect(detail.support_reply_draft?.status).toBe('sent')
  })

  it('builds ticket URLs from default and custom API bases', () => {
    expect(ticketListUrl('http://ops-workbench.internal:8000/')).toBe(
      'http://ops-workbench.internal:8000/api/v1/tickets',
    )
    expect(ticketDetailUrl('TCK-20260715-ABCDEF12', 'https://tickets.example.com')).toBe(
      'https://tickets.example.com/api/v1/tickets/TCK-20260715-ABCDEF12',
    )
  })

  it('derives websocket URLs from HTTP URLs', () => {
    expect(toWebSocketUrl('http://127.0.0.1:8000')).toBe('ws://127.0.0.1:8000')
    expect(toWebSocketUrl('https://example.com/')).toBe('wss://example.com')
    expect(processTicketWsUrl('https://tickets.example.com/')).toBe(
      'wss://tickets.example.com/api/v1/tickets/process/ws',
    )
  })
})
