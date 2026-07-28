import { Search } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'

import { useAuth } from '../../app/AuthProvider'
import { listQueue } from '../../api/workflow'
import { TicketList } from '../../features/tickets/TicketList'
import type { TicketListItem } from '../../types/workflow'

export function OperatorQueuePage(): JSX.Element {
  const auth = useAuth()
  const [items, setItems] = useState<TicketListItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [query, setQuery] = useState('')
  const [priority, setPriority] = useState('all')

  useEffect(() => { if (auth.token) listQueue(auth.token).then((result) => setItems(result.items)).catch((caught) => setError(caught instanceof Error ? caught.message : '加载失败')).finally(() => setLoading(false)) }, [auth.token])
  const filtered = useMemo(() => items.filter((item) => (priority === 'all' || item.priority === priority) && (!query.trim() || `${item.ticket_id} ${item.summary ?? ''} ${item.affected_service ?? ''}`.toLowerCase().includes(query.trim().toLowerCase()))), [items, priority, query])

  return <div className="page-stack"><header className="page-header"><div><span className="eyebrow">运维工作台</span><h1>待处理队列</h1><p>按 SLA 和优先级检查尚未认领的请求。</p></div><div className="page-stat"><strong>{items.length}</strong><span>待处理</span></div></header><section className="toolbar"><label className="search-field"><Search size={17} /><input aria-label="搜索待处理工单" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="搜索工单号、主题或服务" /></label><select aria-label="优先级筛选" value={priority} onChange={(e) => setPriority(e.target.value)}><option value="all">全部优先级</option><option>P1</option><option>P2</option><option>P3</option><option>P4</option></select></section>{error && <div className="error-banner">{error}</div>}<TicketList items={filtered} loading={loading} detailBase="/operator/tickets" emptyTitle="队列已清空" /></div>
}
