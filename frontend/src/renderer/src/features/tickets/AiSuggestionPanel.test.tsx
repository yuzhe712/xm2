import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { AiRun } from '../../types/workflow'
import { AiSuggestionPanel } from './AiSuggestionPanel'

const run: AiRun = {
  id: 'RUN-20260728-ABCDEF12', ticket_id: 'TCK-20260728-ABCDEF12', status: 'completed',
  stage: 'quality_gate', progress: 100, pipeline_version: 'p2-v1', provider: 'test',
  model: 'test-model', prompt_version: 'prompt-v1', confidence: 0.82, error_code: null,
  error_message: null, duration_ms: 1200, decision: null, retry_count: 0,
  created_at: '2026-07-28T08:00:00Z', updated_at: '2026-07-28T08:01:00Z', evidence: [],
  result: {
    triage: { classification: { category: 'access', priority: 'P2' } },
    retrieve_diagnose: { diagnosis: { candidate_root_causes: [{ cause: '权限组缺失' }] } },
    quality_gate: { suggested_reply: '请重新登录验证。', recommended_team: 'IT 运维组' },
  },
}

describe('AiSuggestionPanel', () => {
  it('supports accepting a persisted suggestion', () => {
    const decide = vi.fn()
    render(<AiSuggestionPanel run={run} loading={false} onRerun={vi.fn()} onDecision={decide} />)
    fireEvent.click(screen.getByRole('button', { name: '接受建议' }))
    expect(decide).toHaveBeenCalledWith('accepted', '', null)
  })

  it('sends the edited reply as a modified result', () => {
    const decide = vi.fn()
    render(<AiSuggestionPanel run={run} loading={false} onRerun={vi.fn()} onDecision={decide} />)
    fireEvent.change(screen.getByLabelText('编辑 AI 建议回复'), { target: { value: '已人工修改回复。' } })
    fireEvent.click(screen.getByRole('button', { name: '修改后采用' }))
    expect(decide.mock.calls[0][0]).toBe('modified')
    expect(decide.mock.calls[0][2].quality_gate.suggested_reply).toBe('已人工修改回复。')
  })

  it('keeps rerun available when a run failed', () => {
    const rerun = vi.fn()
    render(<AiSuggestionPanel run={{ ...run, status: 'failed', error_message: '模型超时' }} loading={false} onRerun={rerun} onDecision={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: '重新运行 AI' }))
    expect(rerun).toHaveBeenCalledOnce()
    expect(screen.getByText('模型超时')).toBeInTheDocument()
  })
})
