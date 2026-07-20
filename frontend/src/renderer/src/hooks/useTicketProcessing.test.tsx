import { act, renderHook } from '@testing-library/react'
import { beforeEach, describe, expect, it } from 'vitest'

import { useTicketProcessing } from './useTicketProcessing'
import type { TicketHistoryDetailResponse, TicketProcessWsCompletedEvent } from '../types/tickets'

class MockWebSocket {
  static instances: MockWebSocket[] = []
  static OPEN = 1
  readyState = MockWebSocket.OPEN
  sent: string[] = []
  url: string
  private listeners = new Map<string, Array<(event: { data?: string }) => void>>()

  constructor(url: string) {
    this.url = url
    MockWebSocket.instances.push(this)
  }

  addEventListener(type: string, listener: (event: { data?: string }) => void): void {
    const current = this.listeners.get(type) ?? []
    current.push(listener)
    this.listeners.set(type, current)
  }

  send(message: string): void {
    this.sent.push(message)
  }

  emit(type: string, data?: unknown): void {
    for (const listener of this.listeners.get(type) ?? []) {
      listener({ data: data === undefined ? undefined : JSON.stringify(data) })
    }
  }
}

const response = {
  ticket_id: 'TCK-001',
  run_id: 'RUN-001',
  data_mode: 'mock' as const,
  classification: {
    category: 'ops_alert',
    summary: 'summary',
    affected_service: 'payment-service',
    symptoms: [],
    priority: 'P1',
    priority_reason: 'reason',
    extracted_metrics: {},
    evidence_ids: [],
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
  routing: { recommended_team: null, recommended_actions: [], escalation: '', sop_refs: [] },
  report: {
    title: '报告',
    summary: 'summary',
    facts: [],
    derived_findings: [],
    assumptions: [],
    unknowns: [],
    recommendations: [],
  },
  agent_trace: [],
  evidence: [],
}

const completedEvent: TicketProcessWsCompletedEvent = {
  type: 'completed',
  ticket_id: 'TCK-001',
  run_id: 'RUN-001',
  sequence: 3,
  timestamp: 'now',
  result: response,
}

function historyDetail(status: 'completed' | 'failed' | 'cancelled'): TicketHistoryDetailResponse {
  return {
    ticket_id: 'TCK-001',
    desk_id: 'ops',
    input_text: '测试工单',
    data_mode: 'mock',
    ticket_status: status === 'cancelled' ? 'cancelled' : status === 'completed' ? 'resolved' : 'open',
    created_at: 'now',
    updated_at: 'now',
    latest_run: {
      run_id: 'RUN-001',
      status,
      data_mode: 'mock',
      route_mode: 'deterministic',
      started_at: 'now',
      completed_at: 'now',
      response: status === 'completed' ? response : null,
      error: status === 'completed' ? null : { code: 'RUN_FAILED', message: 'failed', details: {} },
      agent_runs: [
        {
          sequence: 1,
          task_id: 'TASK-001',
          agent_name: 'ticket_intake_agent',
          step: 'ticket_intake',
          status,
          route_decision: null,
          observations: ['observed'],
          evidence_ids: ['ev_ticket_input_001'],
          error: null,
          started_at: 'now',
          completed_at: 'now',
        },
      ],
      supervisor_decisions: [],
      evidence: [],
    },
  }
}

describe('useTicketProcessing', () => {
  beforeEach(() => {
    MockWebSocket.instances = []
    // @ts-expect-error Test replaces browser WebSocket with a controllable mock.
    globalThis.WebSocket = MockWebSocket
  })

  it('uses the active backend URL for WebSocket processing', () => {
    const { result } = renderHook(() =>
      useTicketProcessing({ apiBaseUrl: 'https://tickets.example.com/api-root/' }),
    )

    act(() => result.current.runWebSocket('测试工单', 'support'))

    expect(MockWebSocket.instances[0].url).toBe('wss://tickets.example.com/api-root/api/v1/tickets/process/ws')
  })

  it('sends cancel message with best-effort reason', () => {
    const { result } = renderHook(() => useTicketProcessing())

    act(() => result.current.runWebSocket('测试工单', 'support'))
    const socket = MockWebSocket.instances[0]
    act(() => socket.emit('open'))
    act(() => result.current.cancelWebSocket())

    expect(JSON.parse(socket.sent[1])).toEqual({ type: 'cancel', reason: 'user_cancelled' })
    expect(result.current.cancelExplanation).toContain('取消请求已发送')
  })

  it('shows completed persisted detail', () => {
    const { result } = renderHook(() => useTicketProcessing())

    act(() => result.current.showPersistedDetail(historyDetail('completed')))

    expect(result.current.mode).toBe('completed')
    expect(result.current.result?.ticket_id).toBe('TCK-001')
    expect(result.current.historyDetail?.latest_run?.status).toBe('completed')
    expect(result.current.storedAgentRuns).toHaveLength(1)
  })

  it('shows failed persisted detail without stale result', () => {
    const { result } = renderHook(() => useTicketProcessing())

    act(() => result.current.showPersistedDetail(historyDetail('failed')))

    expect(result.current.mode).toBe('error')
    expect(result.current.result).toBeNull()
    expect(result.current.error).toMatchObject({ code: 'RUN_FAILED' })
    expect(result.current.storedAgentRuns[0].observations).toContain('observed')
  })

  it('shows cancelled persisted detail without a fake result', () => {
    const { result } = renderHook(() => useTicketProcessing())

    act(() => result.current.showPersistedDetail(historyDetail('cancelled')))

    expect(result.current.mode).toBe('cancelled')
    expect(result.current.result).toBeNull()
    expect(result.current.cancelExplanation).toContain('历史运行已取消')
    expect(result.current.storedAgentRuns).toHaveLength(1)
  })

  it('treats completed after cancel as valid best-effort completion', () => {
    const { result } = renderHook(() => useTicketProcessing())

    act(() => result.current.runWebSocket('测试工单', 'support'))
    const socket = MockWebSocket.instances[0]
    act(() => socket.emit('open'))
    act(() => result.current.cancelWebSocket())
    act(() => socket.emit('message', completedEvent))

    expect(result.current.mode).toBe('completed')
    expect(result.current.cancelExplanation).toContain('best-effort')
  })
})
