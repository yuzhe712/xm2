import { useEffect, useMemo, useState } from 'react'

import type {
  FinalReport,
  RoutingRecommendation,
  SupportReplyDraftResponse,
  SupportReplyDraftStatus,
  SupportReplyDraftUpdateRequest,
  SupportTicketResult,
} from '../types/tickets'
import { EvidenceRefPill } from './EvidenceRefPill'

const DRAFT_STATUS_LABELS: Record<SupportReplyDraftStatus, string> = {
  draft: '草稿',
  approved: '已审核',
  sent: '本地已发送',
  discarded: '已废弃',
}

interface SupportReplyPanelProps {
  report?: FinalReport
  routing?: RoutingRecommendation
  supportResult?: SupportTicketResult | null
  draft?: SupportReplyDraftResponse | null
  saving?: boolean
  onSaveDraft?: (request: SupportReplyDraftUpdateRequest) => void
  onEvidenceSelect?: (evidenceId: string) => void
}

export function SupportReplyPanel({
  report,
  routing,
  supportResult,
  draft,
  saving = false,
  onSaveDraft,
  onEvidenceSelect,
}: SupportReplyPanelProps): JSX.Element | null {
  const initialText = useMemo(() => {
    if (draft?.reply_text) return draft.reply_text
    if (supportResult?.reply_suggestions?.length) return supportResult.reply_suggestions.join('\n')
    if (report?.recommendations?.length) return report.recommendations.join('\n')
    return ''
  }, [draft?.reply_text, report?.recommendations, supportResult?.reply_suggestions])
  const [replyText, setReplyText] = useState(initialText)
  const [reportSummary, setReportSummary] = useState(draft?.report_summary ?? report?.summary ?? '')

  useEffect(() => {
    setReplyText(initialText)
  }, [initialText])

  useEffect(() => {
    setReportSummary(draft?.report_summary ?? report?.summary ?? '')
  }, [draft?.report_summary, report?.summary])

  if (!report && !routing && !supportResult && !draft) return null

  const recommendedTeam = supportResult?.recommended_team ?? routing?.recommended_team ?? '内部支持服务台'
  const escalation = supportResult?.escalation ?? routing?.escalation
  const articleRefs = supportResult?.matched_articles ?? routing?.sop_refs ?? []
  const replySuggestions = supportResult?.reply_suggestions ?? report?.recommendations ?? []
  const evidenceIds = draft?.evidence_ids?.length
    ? draft.evidence_ids
    : Array.from(new Set([
      ...(supportResult?.evidence_ids ?? []),
      ...(routing?.recommended_actions.flatMap((action) => action.evidence_ids) ?? []),
    ]))
  const draftStatus = draft?.status ?? 'draft'
  const canSave = Boolean(onSaveDraft) && replyText.trim().length > 0 && !saving

  function submit(status: SupportReplyDraftStatus): void {
    if (!onSaveDraft) return
    onSaveDraft({
      reply_text: replyText,
      report_summary: reportSummary.trim() || null,
      evidence_ids: evidenceIds,
      status,
      editor: 'local-operator',
    })
  }

  return (
    <section className="panel support-reply-panel">
      <div className="panel-heading-row">
        <div>
          <h2>内部支持回复草稿</h2>
          <p className="muted">可编辑草稿保留与最新 deterministic AI run 的 evidence 关系。</p>
        </div>
        <span className="status-chip">{DRAFT_STATUS_LABELS[draftStatus]}</span>
      </div>
      <p className="notice">“标记本地已发送”只表示本地/mock 工作流状态，不代表已发送到真实外部工单或消息系统。</p>
      {report && (
        <>
          <h3 className="report-title">{report.title}</h3>
          <p className="report-summary">{report.summary}</p>
        </>
      )}
      <dl className="details-grid">
        <dt>推荐团队</dt>
        <dd>{recommendedTeam}</dd>
        <dt>升级条件</dt>
        <dd>{escalation ?? '暂无'}</dd>
        <dt>知识库引用</dt>
        <dd>{articleRefs.length > 0 ? articleRefs.join('、') : '无'}</dd>
        <dt>草稿来源</dt>
        <dd>{draft?.source ?? 'deterministic suggestion seed'}</dd>
        <dt>更新时间</dt>
        <dd>{draft?.updated_at ?? '尚未保存'}</dd>
      </dl>
      {replySuggestions.length > 0 && (
        <div className="list-block">
          <h3>AI 建议回复种子</h3>
          <ol>
            {replySuggestions.map((item, index) => (
              <li key={`${item}-${index}`}>{item}</li>
            ))}
          </ol>
        </div>
      )}
      <label className="field-block">
        <span>可编辑回复</span>
        <textarea
          value={replyText}
          onChange={(event) => setReplyText(event.target.value)}
          rows={7}
          placeholder="编辑要回复给用户的内容"
        />
      </label>
      <label className="field-block">
        <span>报告摘要</span>
        <textarea
          value={reportSummary}
          onChange={(event) => setReportSummary(event.target.value)}
          rows={3}
          placeholder="可选：保存人工调整后的报告摘要"
        />
      </label>
      {evidenceIds.length > 0 && (
        <div className="list-block">
          <h3>草稿证据引用</h3>
          <div className="evidence-ref-list">
            {evidenceIds.map((evidenceId) => (
              <EvidenceRefPill key={evidenceId} evidenceId={evidenceId} onSelect={onEvidenceSelect} />
            ))}
          </div>
        </div>
      )}
      <div className="button-row compact-buttons">
        <button type="button" disabled={!canSave} onClick={() => submit('draft')}>
          保存草稿
        </button>
        <button type="button" disabled={!canSave} onClick={() => submit('approved')}>
          标记已审核
        </button>
        <button type="button" disabled={!canSave} onClick={() => submit('sent')}>
          标记本地已发送
        </button>
      </div>
      {routing && routing.recommended_actions.length > 0 && (
        <div className="list-block">
          <h3>处理动作</h3>
          <ul>
            {routing.recommended_actions.map((action, index) => (
              <li key={`${action.action}-${index}`}>
                <span>{action.action}</span>
                {action.evidence_ids.length > 0 && (
                  <div className="evidence-ref-list">
                    {action.evidence_ids.map((evidenceId) => (
                      <EvidenceRefPill
                        key={evidenceId}
                        evidenceId={evidenceId}
                        onSelect={onEvidenceSelect}
                      />
                    ))}
                  </div>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  )
}
