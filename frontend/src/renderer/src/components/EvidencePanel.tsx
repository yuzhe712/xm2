import type { Evidence } from '../types/tickets'
import { MockDataBadge } from './MockDataBadge'

interface EvidencePanelProps {
  evidence: Evidence[]
  selectedEvidenceId?: string | null
  onSelectEvidence?: (evidenceId: string) => void
}

export function EvidencePanel({
  evidence,
  selectedEvidenceId,
  onSelectEvidence,
}: EvidencePanelProps): JSX.Element {
  return (
    <section className="panel evidence-panel">
      <h2>证据</h2>
      {evidence.length === 0 && <p className="muted">暂无证据。</p>}
      <div className="evidence-list">
        {evidence.map((item) => {
          const isSelected = selectedEvidenceId === item.evidence_id
          return (
            <details
              key={item.evidence_id}
              id={`evidence-${item.evidence_id}`}
              className={`evidence-card${isSelected ? ' evidence-card-selected' : ''}`}
              open={isSelected || undefined}
              onClick={() => onSelectEvidence?.(item.evidence_id)}
            >
              <summary className="evidence-card-header">
                <strong>{item.evidence_id}</strong>
                <MockDataBadge mode={item.data_mode} />
              </summary>
              <p>{item.summary}</p>
              <dl className="details-grid compact">
                <dt>来源</dt>
                <dd>{item.source_type} / {item.source_name}</dd>
                <dt>服务</dt>
                <dd>{item.service ?? '无'}</dd>
                <dt>指标</dt>
                <dd>
                  {item.metric_name
                    ? `${item.metric_name}: ${String(item.value ?? '-')}${item.unit ?? ''}`
                    : '无'}
                </dd>
                <dt>质量</dt>
                <dd>{item.quality}</dd>
                <dt>时效</dt>
                <dd>{item.freshness ?? '未提供'}</dd>
                <dt>质量说明</dt>
                <dd>{item.quality_reason ?? '未提供'}</dd>
                <dt>生成方</dt>
                <dd>{item.producer ?? '未提供'}</dd>
                <dt>运行</dt>
                <dd>{item.run_id ?? '未提供'}</dd>
                <dt>追踪 URI</dt>
                <dd>{item.trace_uri ? <a href={item.trace_uri}>{item.trace_uri}</a> : '未提供'}</dd>
                <dt>时间</dt>
                <dd>{item.observed_at ?? item.retrieved_at ?? '未知'}</dd>
              </dl>
            </details>
          )
        })}
      </div>
    </section>
  )
}
