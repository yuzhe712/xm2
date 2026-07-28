import { useEffect, useState } from 'react'
import { useAuth } from '../../app/AuthProvider'
import { listAllTickets } from '../../api/workflow'
import { TicketList } from '../../features/tickets/TicketList'
import type { TicketListItem } from '../../types/workflow'

export function OperatorWorkPage(): JSX.Element {
  const auth = useAuth()
  const [items, setItems] = useState<TicketListItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => { if (auth.token) listAllTickets(auth.token).then((result) => setItems(result.items.filter((item) => item.assignee_id === auth.user?.id && ['in_progress', 'resolved'].includes(item.ticket_status)))).catch((caught) => setError(caught instanceof Error ? caught.message : '加载失败')).finally(() => setLoading(false)) }, [auth.token, auth.user?.id])
  return <div className="page-stack"><header className="page-header"><div><span className="eyebrow">运维工作台</span><h1>我的工作</h1><p>集中处理已认领工单和等待提交人确认的结果。</p></div><div className="page-stat"><strong>{items.length}</strong><span>当前负责</span></div></header>{error && <div className="error-banner">{error}</div>}<TicketList items={items} loading={loading} detailBase="/operator/tickets" emptyTitle="当前没有负责的工单" /></div>
}
