import type { ReviewResult } from '../types/tickets'
import { EvidenceRefPill } from './EvidenceRefPill'

interface ReviewerPanelProps {
  review: ReviewResult | null | undefined
  onEvidenceSelect?: (evidenceId: string) => void
}

const STATUS_LABELS: Record<string, { label: string; cls: string }> = {
  consistent: { label: '✅ 一致', cls: 'review-consistent' },
  flagged: { label: '⚠️ 发现问题', cls: 'review-flagged' },
  abstain: { label: '⊘ 审查跳过', cls: 'review-abstain' },
}

const SEVERITY_LABELS: Record<string, string> = {
  critical: '🔴',
  warning: '🟡',
  info: '🔵',
}

export function ReviewerPanel({ review, onEvidenceSelect }: ReviewerPanelProps): JSX.Element | null {
  if (!review) return null

  const statusInfo = STATUS_LABELS[review.review_status] ?? STATUS_LABELS.abstain

  return (
    <section className="panel reviewer-panel">
      <div className="panel-heading-row">
        <h2>🔍 证据一致性审查</h2>
        <span className={`status-chip ${statusInfo.cls}`}>{statusInfo.label}</span>
      </div>

      <dl className="details-grid compact">
        <dt>建议</dt>
        <dd>{review.recommendation}</dd>
        <dt>置信度</dt>
        <dd>{(review.confidence * 100).toFixed(0)}%</dd>
      </dl>

      {review.issues.length > 0 && (
        <div className="review-issues">
          <h3>发现的问题 ({review.issues.length})</h3>
          <ul className="review-issue-list">
            {review.issues.map((issue, index) => (
              <li key={index} className={`review-issue-item review-issue-${issue.severity}`}>
                <div className="review-issue-header">
                  <span className="review-issue-severity">
                    {SEVERITY_LABELS[issue.severity] ?? '⚪'} {issue.category}
                  </span>
                </div>
                <p>{issue.description}</p>
                {issue.affected_fields.length > 0 && (
                  <div className="review-issue-fields">
                    影响字段：{issue.affected_fields.join(', ')}
                  </div>
                )}
                {issue.evidence_ids.length > 0 && (
                  <div className="evidence-ref-list">
                    {issue.evidence_ids.map((eid) => (
                      <EvidenceRefPill key={eid} evidenceId={eid} onSelect={onEvidenceSelect} />
                    ))}
                  </div>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      {review.issues.length === 0 && (
        <p className="muted">未发现跨 Agent 证据链矛盾，诊断与路由一致。</p>
      )}

      {review.evidence_ids.length > 0 && (
        <div className="evidence-ref-list" style={{ marginTop: '0.75rem' }}>
          <span className="muted">审查引用证据：</span>
          {review.evidence_ids.map((eid) => (
            <EvidenceRefPill key={eid} evidenceId={eid} onSelect={onEvidenceSelect} />
          ))}
        </div>
      )}
    </section>
  )
}
