import type { RoutingRecommendation } from '../types/tickets'
import { EvidenceRefPill } from './EvidenceRefPill'

interface RoutingPanelProps {
  routing?: RoutingRecommendation
  onEvidenceSelect?: (evidenceId: string) => void
}

export function RoutingPanel({ routing, onEvidenceSelect }: RoutingPanelProps): JSX.Element | null {
  if (!routing) return null
  return (
    <section className="panel routing-panel">
      <h2>分派建议</h2>
      <dl className="details-grid">
        <dt>推荐团队</dt>
        <dd>{routing.recommended_team ?? '待人工确认'}</dd>
        <dt>升级策略</dt>
        <dd>{routing.escalation}</dd>
        <dt>SOP</dt>
        <dd>{routing.sop_refs.length > 0 ? routing.sop_refs.join('、') : '无'}</dd>
      </dl>
      <h3>行动项</h3>
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
    </section>
  )
}
