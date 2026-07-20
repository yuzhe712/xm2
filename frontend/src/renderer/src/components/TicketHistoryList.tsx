import type { TicketHistorySummary, TicketStatus } from '../types/tickets'
import { MockDataBadge } from './MockDataBadge'

const STATUS_LABELS: Record<TicketHistorySummary['status'], string> = {
  completed: '已完成',
  failed: '失败',
  cancelled: '已取消',
  pending: '待处理',
}

const DESK_LABELS: Record<TicketHistorySummary['desk_id'], string> = {
  ops: 'IT 运维',
  support: '内部支持',
}

const TICKET_STATUS_LABELS: Record<TicketStatus, string> = {
  pending: '待处理',
  open: '待处理',
  in_progress: '处理中',
  resolved: '已解决',
  closed: '已关闭',
  cancelled: '已取消',
}

interface TicketHistoryListProps {
  items: TicketHistorySummary[]
  loading: boolean
  total: number
  onSelect: (ticketId: string) => void
  title?: string
  emptyText?: string
  selectedTicketId?: string | null
}

function slaLabel(deadline: string | null | undefined): { text: string; cls: string } {
  if (!deadline) return { text: '—', cls: '' }
  const now = Date.now()
  const target = new Date(deadline).getTime()
  const remain = target - now
  if (remain <= 0) return { text: '已超时', cls: 'sla-overdue' }
  const hours = Math.floor(remain / 3600000)
  const mins = Math.floor((remain % 3600000) / 60000)
  if (hours > 24) return { text: `${Math.floor(hours / 24)}天${hours % 24}时`, cls: 'sla-ok' }
  if (hours > 0) return { text: `${hours}时${mins}分`, cls: hours <= 2 ? 'sla-warn' : 'sla-ok' }
  return { text: `${mins}分`, cls: 'sla-warn' }
}

export function TicketHistoryList({
  items,
  loading,
  total,
  onSelect,
  title = '所有请求',
  emptyText = '暂无历史工单。',
  selectedTicketId = null,
}: TicketHistoryListProps): JSX.Element {
  return (
    <section className="panel requests-panel">
      <div className="panel-heading-row">
        <div>
          <h2>{title}</h2>
          {items.length > 0 && <p className="muted">当前显示 {total} 条已持久化工单。</p>}
        </div>
      </div>
      {loading && <p className="muted">正在加载历史工单...</p>}
      {!loading && items.length === 0 && <p className="muted">{emptyText}</p>}
      {items.length > 0 && (
        <div className="request-table-wrap">
          <table className="request-table" aria-label="历史工单请求列表">
            <thead>
              <tr>
                <th>工单号</th>
                <th>主题 / 服务</th>
                <th>状态</th>
                <th>数据</th>
                <th>优先级</th>
                <th>提交人</th>
                <th>更新时间</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr
                  key={item.ticket_id}
                  className={item.ticket_id === selectedTicketId ? 'selected-row' : undefined}
                >
                  <td className="request-id">{item.ticket_id}</td>
                  <td>
                    <strong>{item.report_title || item.summary}</strong>
                    <span className="request-sub">
                      {item.affected_service ? <span>{item.affected_service}</span> : null}
                      {item.affected_service ? ' · ' : ''}
                      <span>{DESK_LABELS[item.desk_id]}</span>
                    </span>
                  </td>
                  <td>
                    <span className={`status-chip ticket-status-${item.ticket_status}`}>
                      {TICKET_STATUS_LABELS[item.ticket_status]}
                    </span>
                    <span className="request-sub">
                      运行：<span>{STATUS_LABELS[item.status]}</span>
                    </span>
                  </td>
                  <td><MockDataBadge mode={item.data_mode} /></td>
                  <td>
                    <span className="priority-chip">{item.priority || '—'}</span>
                  </td>
                  <td>{item.submitter || '—'}</td>
                  <td className="request-time">{item.updated_at?.replace('T', ' ').slice(0, 16) || ''}</td>
                  <td className="table-actions-cell">
                    <button className="table-action" type="button" onClick={() => onSelect(item.ticket_id)}>
                      查看
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
