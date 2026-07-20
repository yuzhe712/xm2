import type { TicketClassification } from '../types/tickets'
import { EvidenceRefPill } from './EvidenceRefPill'

interface ClassificationPanelProps {
  classification?: TicketClassification
  onEvidenceSelect?: (evidenceId: string) => void
}

export function ClassificationPanel({
  classification,
  onEvidenceSelect,
}: ClassificationPanelProps): JSX.Element | null {
  if (!classification) return null
  return (
    <section className="panel">
      <h2>工单分类</h2>
      <dl className="details-grid">
        <dt>类型</dt>
        <dd>{classification.category}</dd>
        <dt>优先级</dt>
        <dd><span className="badge badge-priority">{classification.priority}</span></dd>
        <dt>影响服务</dt>
        <dd>{classification.affected_service ?? '未知服务'}</dd>
        <dt>症状</dt>
        <dd>{classification.symptoms.join('、')}</dd>
        <dt>优先级理由</dt>
        <dd>{classification.priority_reason}</dd>
      </dl>
      {classification.evidence_ids.length > 0 && (
        <div className="evidence-ref-list">
          {classification.evidence_ids.map((evidenceId) => (
            <EvidenceRefPill
              key={evidenceId}
              evidenceId={evidenceId}
              onSelect={onEvidenceSelect}
            />
          ))}
        </div>
      )}
    </section>
  )
}
