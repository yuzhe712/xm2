import type { StoredAgentRun, TicketProcessWsEvent, WorkflowStepTrace } from '../types/tickets'
import { EvidenceRefPill } from './EvidenceRefPill'

interface AgentTimelineProps {
  events: TicketProcessWsEvent[]
  trace: WorkflowStepTrace[]
  storedRuns?: StoredAgentRun[]
  cancelExplanation?: string | null
  onEvidenceSelect?: (evidenceId: string) => void
}

function eventTitle(event: TicketProcessWsEvent): string {
  if (event.type === 'started') return '开始处理'
  if (event.type === 'agent_progress') return `${event.step} / ${event.agent_name}`
  if (event.type === 'completed') return '处理完成'
  if (event.type === 'cancelled') return '已取消'
  return `错误：${event.error.code}`
}

function eventSummary(event: TicketProcessWsEvent): string {
  if (event.type === 'agent_progress') return event.summary
  if (event.type === 'completed') return '已生成完整报告和证据。'
  if (event.type === 'cancelled') return `取消原因：${event.reason}`
  if (event.type === 'error') return event.error.message
  return `ticket_id=${event.ticket_id}, run_id=${event.run_id}`
}

function routeDecisionSummary(routeDecision: unknown): string | null {
  if (!routeDecision || typeof routeDecision !== 'object') return null
  const item = routeDecision as { next_agent?: unknown; reason_summary?: unknown }
  const nextAgent = typeof item.next_agent === 'string' ? item.next_agent : '未知下一步'
  const reason = typeof item.reason_summary === 'string' ? item.reason_summary : '无原因摘要'
  return `${nextAgent}：${reason}`
}

export function AgentTimeline({
  events,
  trace,
  storedRuns = [],
  cancelExplanation,
  onEvidenceSelect,
}: AgentTimelineProps): JSX.Element {
  const hasLiveEvents = events.length > 0
  const hasStoredRuns = storedRuns.length > 0
  return (
    <section className="panel timeline-panel">
      <h2>Agent 执行链路</h2>
      {cancelExplanation && <p className="notice">{cancelExplanation}</p>}
      {!hasLiveEvents && !hasStoredRuns && trace.length === 0 && <p className="muted">尚未开始处理。</p>}
      {hasLiveEvents && (
        <ol className="timeline" aria-label="实时 Agent 进度">
          {events.map((event, index) => (
            <li key={`${event.type}-${event.sequence}-${index}`}>
              <div className="timeline-title">{eventTitle(event)}</div>
              <div className="timeline-summary">{eventSummary(event)}</div>
              {event.type === 'agent_progress' && event.evidence_refs.length > 0 && (
                <div className="evidence-ref-list">
                  {event.evidence_refs.map((ref) => (
                    <EvidenceRefPill
                      key={ref.evidence_id}
                      evidenceId={ref.evidence_id}
                      onSelect={onEvidenceSelect}
                    />
                  ))}
                </div>
              )}
            </li>
          ))}
        </ol>
      )}
      {!hasLiveEvents && hasStoredRuns && (
        <ol className="timeline" aria-label="持久化 Agent run">
          {storedRuns.map((run) => {
            const routeSummary = routeDecisionSummary(run.route_decision)
            return (
              <li key={`${run.sequence}-${run.task_id}`}>
                <details>
                  <summary>
                    <span className="timeline-title">
                      #{run.sequence} {run.step} / {run.agent_name} — {run.status}
                    </span>
                  </summary>
                  <dl className="details-grid compact">
                    <dt>开始</dt>
                    <dd>{run.started_at}</dd>
                    <dt>结束</dt>
                    <dd>{run.completed_at ?? '未知'}</dd>
                    {routeSummary && (
                      <>
                        <dt>路由</dt>
                        <dd>{routeSummary}</dd>
                      </>
                    )}
                  </dl>
                  {run.react_steps && run.react_steps.length > 0 && (
                    <>
                      <h3>💭 ReAct 推理步骤</h3>
                      <ol className="react-steps-list">
                        {run.react_steps.map((rs) => (
                          <li key={`${run.task_id}-react-${rs.step_index}`} className="react-step-item">
                            <div className="react-step-header">
                              <span className="react-step-badge">Step {rs.step_index}</span>
                              <span className="react-step-action">{rs.action}</span>
                            </div>
                            <p className="react-thought">{rs.decision_summary}</p>
                            {rs.observation_summary && (
                              <p className="react-observation">{rs.observation_summary}</p>
                            )}
                            {rs.evidence_ids.length > 0 && (
                              <div className="evidence-ref-list">
                                {rs.evidence_ids.map((eid) => (
                                  <EvidenceRefPill key={eid} evidenceId={eid} onSelect={onEvidenceSelect} />
                                ))}
                              </div>
                            )}
                          </li>
                        ))}
                      </ol>
                    </>
                  )}
                  {run.observations.length > 0 && (
                    <>
                      <h3>Observations</h3>
                      <ul>
                        {run.observations.map((observation, index) => (
                          <li key={`${run.task_id}-observation-${index}`}>{observation}</li>
                        ))}
                      </ul>
                    </>
                  )}
                  {run.error && (
                    <article className="sub-card">
                      <h3>Agent 错误</h3>
                      <p>{run.error.code}：{run.error.message}</p>
                      {Object.keys(run.error.details).length > 0 && (
                        <pre>{JSON.stringify(run.error.details, null, 2)}</pre>
                      )}
                    </article>
                  )}
                  {run.evidence_ids.length > 0 && (
                    <div className="evidence-ref-list">
                      {run.evidence_ids.map((evidenceId) => (
                        <EvidenceRefPill
                          key={evidenceId}
                          evidenceId={evidenceId}
                          onSelect={onEvidenceSelect}
                        />
                      ))}
                    </div>
                  )}
                </details>
              </li>
            )
          })}
        </ol>
      )}
      {!hasLiveEvents && !hasStoredRuns && trace.length > 0 && (
        <ol className="timeline" aria-label="REST Agent trace">
          {trace.map((item) => (
            <li key={item.step}>
              <div className="timeline-title">{item.step}</div>
              <div className="timeline-summary">{item.summary}</div>
              <div className="evidence-ref-list">
                {item.evidence_ids.map((evidenceId) => (
                  <EvidenceRefPill
                    key={evidenceId}
                    evidenceId={evidenceId}
                    onSelect={onEvidenceSelect}
                  />
                ))}
              </div>
            </li>
          ))}
        </ol>
      )}
    </section>
  )
}
