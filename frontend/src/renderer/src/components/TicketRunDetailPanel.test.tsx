import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { TicketRunDetailPanel } from './TicketRunDetailPanel'
import type { TicketHistoryDetailResponse } from '../types/tickets'

const failedDetail: TicketHistoryDetailResponse = {
  ticket_id: 'TCK-20260715-ABCDEF12',
  desk_id: 'ops',
  input_text: '测试工单',
  data_mode: 'mock',
  ticket_status: 'open',
  created_at: 'created',
  updated_at: 'updated',
  latest_run: {
    run_id: 'RUN-20260715-1234ABCD',
    status: 'failed',
    data_mode: 'mock',
    route_mode: 'deterministic',
    started_at: 'start',
    completed_at: 'end',
    response: null,
    error: { code: 'AGENT_TASK_FAILED', message: 'Agent failed', details: { agent: 'intake' } },
    agent_runs: [],
    supervisor_decisions: [],
    evidence: [],
  },
}

describe('TicketRunDetailPanel', () => {
  it('renders failed run metadata and structured error', () => {
    render(<TicketRunDetailPanel detail={failedDetail} />)

    expect(screen.getByText('历史运行详情')).toBeInTheDocument()
    expect(screen.getByText('TCK-20260715-ABCDEF12')).toBeInTheDocument()
    expect(screen.getByText('失败')).toBeInTheDocument()
    expect(screen.getByText('AGENT_TASK_FAILED')).toBeInTheDocument()
    expect(screen.getByText('该运行未生成完整处理结果，不会展示伪造报告。')).toBeInTheDocument()
  })
})
