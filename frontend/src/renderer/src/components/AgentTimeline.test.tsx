import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { AgentTimeline } from './AgentTimeline'
import type { StoredAgentRun, TicketProcessWsEvent } from '../types/tickets'

const events: TicketProcessWsEvent[] = [
  { type: 'started', ticket_id: 'TCK-001', run_id: 'RUN-001', sequence: 1, timestamp: 'now' },
  ...['ticket_intake', 'context_retrieval', 'diagnosis', 'routing', 'report'].map(
    (step, index) => ({
      type: 'agent_progress' as const,
      ticket_id: 'TCK-001',
      run_id: 'RUN-001',
      sequence: index + 2,
      timestamp: 'now',
      agent_name: `${step}_agent`,
      step,
      status: 'completed',
      summary: `${step} completed`,
      evidence_refs: [],
    }),
  ),
  {
    type: 'completed',
    ticket_id: 'TCK-001',
    run_id: 'RUN-001',
    sequence: 7,
    timestamp: 'now',
    result: {} as never,
  },
]

const storedRuns: StoredAgentRun[] = [
  {
    sequence: 1,
    task_id: 'TASK-001',
    agent_name: 'ticket_intake_agent',
    step: 'ticket_intake',
    status: 'failed',
    route_decision: { next_agent: 'ticket_intake_agent', reason_summary: '选择 intake' },
    observations: ['观察到输入缺少服务名'],
    evidence_ids: ['ev_ticket_input_001'],
    error: { code: 'INTAKE_FAILED', message: 'intake failed', details: { field: 'service' } },
    started_at: 'start',
    completed_at: 'end',
  },
]

describe('AgentTimeline', () => {
  it('renders started, five agent progress events, and completed', () => {
    render(<AgentTimeline events={events} trace={[]} />)

    expect(screen.getByText('开始处理')).toBeInTheDocument()
    expect(screen.getByText('处理完成')).toBeInTheDocument()
    expect(screen.getAllByText(/completed/)).toHaveLength(5)
  })

  it('renders expandable persisted agent runs', () => {
    render(<AgentTimeline events={[]} trace={[]} storedRuns={storedRuns} />)

    expect(screen.getAllByText(/ticket_intake_agent/).length).toBeGreaterThan(0)
    expect(screen.getByText('观察到输入缺少服务名')).toBeInTheDocument()
    expect(screen.getByText(/INTAKE_FAILED/)).toBeInTheDocument()
    expect(screen.getByText('ev_ticket_input_001')).toBeInTheDocument()
  })

  it('renders cancellation terminal state', () => {
    render(
      <AgentTimeline
        events={[
          {
            type: 'cancelled',
            ticket_id: 'TCK-001',
            run_id: 'RUN-001',
            sequence: 2,
            timestamp: 'now',
            reason: 'client_cancelled',
          },
        ]}
        trace={[]}
      />,
    )

    expect(screen.getByText('已取消')).toBeInTheDocument()
  })
})
