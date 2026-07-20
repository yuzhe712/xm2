import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { SupportReplyPanel } from './SupportReplyPanel'

const report = {
  title: '内部支持回复建议：账号权限问题处理说明',
  summary: '已基于 support 服务台知识库生成回复建议。',
  facts: [],
  derived_findings: [],
  assumptions: [],
  unknowns: [],
  recommendations: ['确认申请人所属团队和申请系统'],
}

const routing = {
  recommended_team: '内部支持服务台',
  recommended_actions: [
    { action: '确认申请人所属团队和申请系统', evidence_ids: ['ev_kb_support_account_001'] },
  ],
  escalation: '若涉及高危角色则升级复核。',
  sop_refs: ['KB-SUPPORT-ACCOUNT-PERMISSION'],
}

const supportResult = {
  request_type: 'internal_support_request',
  matched_articles: ['KB-SUPPORT-ACCOUNT-PERMISSION'],
  reply_suggestions: ['确认申请人所属团队和申请系统'],
  recommended_team: '内部支持服务台',
  escalation: '若涉及高危角色则升级复核。',
  evidence_ids: ['ev_kb_support_account_001'],
}

describe('SupportReplyPanel', () => {
  it('renders editable draft seeded from deterministic suggestions', () => {
    const onSaveDraft = vi.fn()
    render(
      <SupportReplyPanel
        report={report}
        routing={routing}
        supportResult={supportResult}
        onSaveDraft={onSaveDraft}
      />,
    )

    const editor = screen.getByLabelText('可编辑回复')
    expect(editor).toHaveValue('确认申请人所属团队和申请系统')
    fireEvent.change(editor, { target: { value: '请补充所属团队后继续处理。' } })
    fireEvent.click(screen.getByRole('button', { name: '保存草稿' }))

    expect(onSaveDraft).toHaveBeenCalledWith(expect.objectContaining({
      reply_text: '请补充所属团队后继续处理。',
      evidence_ids: ['ev_kb_support_account_001'],
      status: 'draft',
    }))
  })

  it('uses persisted draft and marks local sent explicitly', () => {
    const onSaveDraft = vi.fn()
    render(
      <SupportReplyPanel
        report={report}
        routing={routing}
        supportResult={supportResult}
        draft={{
          draft_id: 'DRF-001',
          ticket_id: 'TCK-20260715-ABCDEF12',
          run_id: 'RUN-20260715-1234ABCD',
          source: 'human_edited_from_deterministic_suggestion',
          reply_text: '人工编辑后的回复',
          report_summary: '人工摘要',
          evidence_ids: ['ev_kb_support_account_001'],
          status: 'approved',
          editor: 'local-operator',
          created_at: 'now',
          updated_at: 'now',
          approved_at: 'now',
          sent_at: null,
        }}
        onSaveDraft={onSaveDraft}
      />,
    )

    expect(screen.getByText('“标记本地已发送”只表示本地/mock 工作流状态，不代表已发送到真实外部工单或消息系统。')).toBeInTheDocument()
    expect(screen.getByLabelText('可编辑回复')).toHaveValue('人工编辑后的回复')
    fireEvent.click(screen.getByRole('button', { name: '标记本地已发送' }))

    expect(onSaveDraft).toHaveBeenCalledWith(expect.objectContaining({
      reply_text: '人工编辑后的回复',
      report_summary: '人工摘要',
      status: 'sent',
    }))
  })
})
