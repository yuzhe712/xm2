import type { DiagnosisResult } from '../types/tickets'
import { EvidenceRefPill } from './EvidenceRefPill'

interface DiagnosisPanelProps {
  diagnosis?: DiagnosisResult
  onEvidenceSelect?: (evidenceId: string) => void
}

export function DiagnosisPanel({ diagnosis, onEvidenceSelect }: DiagnosisPanelProps): JSX.Element | null {
  if (!diagnosis) return null
  return (
    <section className="panel">
      <h2>诊断</h2>
      {diagnosis.candidate_root_causes.length === 0 && <p className="muted">暂无可信候选根因。</p>}
      {diagnosis.candidate_root_causes.map((cause) => (
        <article key={cause.cause} className="sub-card">
          <h3>{cause.cause}</h3>
          <p>置信度：{Math.round(cause.confidence * 100)}%</p>
          <p>{cause.reasoning_summary}</p>
          <div className="evidence-ref-list">
            {cause.evidence_ids.map((evidenceId) => (
              <EvidenceRefPill
                key={evidenceId}
                evidenceId={evidenceId}
                onSelect={onEvidenceSelect}
              />
            ))}
          </div>
        </article>
      ))}
      {diagnosis.abstentions.length > 0 && <p className="notice">保留意见：{diagnosis.abstentions.join('；')}</p>}
      {diagnosis.unknowns.length > 0 && <p className="muted">未知项：{diagnosis.unknowns.join('；')}</p>}
    </section>
  )
}
