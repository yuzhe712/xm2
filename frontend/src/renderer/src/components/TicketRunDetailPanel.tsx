import type { TicketHistoryDetailResponse } from '../types/tickets'

const STATUS_LABELS: Record<string, string> = {
  completed: '已完成',
  failed: '失败',
  cancelled: '已取消',
  pending: '待处理',
}

interface TicketRunDetailPanelProps {
  detail: TicketHistoryDetailResponse | null
  onProcess?: (ticketId: string, text: string, deskId: string) => void
}

export function TicketRunDetailPanel({ detail, onProcess }: TicketRunDetailPanelProps): JSX.Element | null {
  if (!detail) return null
  const run = detail.latest_run

  if (!run) {
    return (
      <section className="panel">
        <h2>工单详情</h2>
        <dl className="details-grid">
          <dt>工单</dt>
          <dd>{detail.ticket_id}</dd>
          <dt>状态</dt>
          <dd><span className="status-chip status-pending">待处理</span></dd>
          <dt>提交人</dt>
          <dd>{detail.submitter || '未知'}</dd>
          <dt>服务台</dt>
          <dd>{detail.desk_id === 'support' ? '内部支持服务台' : 'IT 运维服务台'}</dd>
          <dt>创建时间</dt>
          <dd>{detail.created_at}</dd>
          <dt>输入</dt>
          <dd>{detail.input_text}</dd>
        </dl>
        {onProcess && (
          <button
            className="button-primary"
            style={{ marginTop: 12 }}
            onClick={() => onProcess(detail.ticket_id, detail.input_text, detail.desk_id)}
          >
            处理此工单
          </button>
        )}
      </section>
    )
  }

  return (
    <section className="panel">
      <h2>历史运行详情</h2>
      <dl className="details-grid">
        <dt>工单</dt>
        <dd>{detail.ticket_id}</dd>
        <dt>运行</dt>
        <dd>{run.run_id}</dd>
        <dt>状态</dt>
        <dd>{STATUS_LABELS[run.status] || run.status}</dd>
        <dt>路由</dt>
        <dd>{run.route_mode}</dd>
        <dt>开始</dt>
        <dd>{run.started_at}</dd>
        <dt>结束</dt>
        <dd>{run.completed_at}</dd>
        <dt>输入</dt>
        <dd>{detail.input_text}</dd>
      </dl>
      {!run.response && (
        <p className="notice">该运行未生成完整处理结果，不会展示伪造报告。</p>
      )}
      {run.error && (
        <article className="sub-card">
          <h3>结构化错误</h3>
          <dl className="details-grid compact">
            <dt>Code</dt>
            <dd>{run.error.code}</dd>
            <dt>Message</dt>
            <dd>{run.error.message}</dd>
          </dl>
          {Object.keys(run.error.details).length > 0 && (
            <pre>{JSON.stringify(run.error.details, null, 2)}</pre>
          )}
        </article>
      )}
    </section>
  )
}
