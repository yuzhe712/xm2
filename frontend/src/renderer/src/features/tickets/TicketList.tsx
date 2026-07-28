import { ChevronRight, Clock3 } from 'lucide-react'
import { Link } from 'react-router-dom'

import type { TicketListItem } from '../../types/workflow'
import { formatDate, isOverdue, statusLabels } from './ticketPresentation'

interface TicketListProps {
  items: TicketListItem[]
  loading: boolean
  detailBase: string
  emptyTitle: string
}

export function TicketList({ items, loading, detailBase, emptyTitle }: TicketListProps): JSX.Element {
  if (loading) return <div className="loading-panel">正在加载工单...</div>
  if (!items.length) return <div className="empty-state"><strong>{emptyTitle}</strong><span>当前没有符合条件的工单。</span></div>

  return (
    <div className="ticket-table" role="table" aria-label="工单列表">
      <div className="ticket-row ticket-row-head" role="row">
        <span>工单</span><span>状态</span><span>优先级</span><span>负责人</span><span>SLA</span><span />
      </div>
      {items.map((item) => {
        const overdue = isOverdue(item.resolution_due_at ?? item.sla_deadline)
        return (
          <Link className="ticket-row" role="row" key={item.ticket_id} to={`${detailBase}/${item.ticket_id}`}>
            <span className="ticket-subject"><strong>{item.summary || '未命名工单'}</strong><small>{item.ticket_id}</small></span>
            <span><span className={`status-badge status-${item.ticket_status}`}>{statusLabels[item.ticket_status]}</span></span>
            <span><span className={`priority priority-${(item.priority ?? 'P3').toLowerCase()}`}>{item.priority ?? 'P3'}</span></span>
            <span>{item.claimed_by ?? '未分配'}</span>
            <span className={overdue ? 'sla-overdue' : 'sla-time'}><Clock3 size={15} aria-hidden="true" />{overdue ? '已超时' : formatDate(item.resolution_due_at ?? item.sla_deadline)}</span>
            <ChevronRight size={17} aria-hidden="true" />
          </Link>
        )
      })}
    </div>
  )
}
