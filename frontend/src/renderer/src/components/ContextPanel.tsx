import type { RetrievedContext } from '../types/tickets'
import { MockDataBadge } from './MockDataBadge'

interface ContextPanelProps {
  context?: RetrievedContext
}

export function ContextPanel({ context }: ContextPanelProps): JSX.Element | null {
  if (!context) return null
  return (
    <section className="panel">
      <h2>上下文</h2>
      {context.service ? (
        <dl className="details-grid">
          <dt>服务</dt>
          <dd>{context.service.display_name} ({context.service.name})</dd>
          <dt>归属团队</dt>
          <dd>{context.service.owner_team}</dd>
          <dt>重要性</dt>
          <dd>{context.service.criticality}</dd>
          <dt>数据模式</dt>
          <dd><MockDataBadge mode={context.service.data_mode} /></dd>
        </dl>
      ) : (
        <p className="muted">未识别服务上下文。</p>
      )}
      <p className="muted">
        指标 {context.metrics.length} 条，部署 {context.deployments.length} 条，历史工单{' '}
        {context.historical_incidents.length} 条，SOP {context.sop_documents.length} 条。
      </p>
      {context.unknowns.length > 0 && <p className="notice">未知项：{context.unknowns.join('；')}</p>}
    </section>
  )
}
