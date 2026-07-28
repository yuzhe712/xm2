import { Search } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'

import { useAuth } from '../../app/AuthProvider'
import { listMine } from '../../api/workflow'
import { TicketList } from '../../features/tickets/TicketList'
import type { TicketListItem } from '../../types/workflow'

export function EmployeeTicketsPage(): JSX.Element {
  const auth = useAuth()
  const [items, setItems] = useState<TicketListItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [query, setQuery] = useState('')
  const [status, setStatus] = useState('active')

  useEffect(() => {
    if (!auth.token) return
    listMine(auth.token).then((result) => setItems(result.items)).catch((caught) => setError(caught instanceof Error ? caught.message : '加载失败')).finally(() => setLoading(false))
  }, [auth.token])

  const filtered = useMemo(() => items.filter((item) => {
    const matchesStatus = status === 'all' || (status === 'active'
      ? ['pending', 'open', 'in_progress', 'resolved'].includes(item.ticket_status)
      : item.ticket_status === status)
    const normalized = query.trim().toLowerCase()
    return matchesStatus && (!normalized || `${item.ticket_id} ${item.summary ?? ''}`.toLowerCase().includes(normalized))
  }), [items, query, status])

  return <div className="page-stack"><header className="page-header"><div><span className="eyebrow">员工门户</span><h1>我的工单</h1><p>查看处理进度并完成解决确认。</p></div><Link className="button-link" to="/employee/tickets/new">新建工单</Link></header>
    <section className="toolbar"><label className="search-field"><Search size={17} /><input aria-label="搜索我的工单" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="搜索工单号或主题" /></label><div className="segmented" aria-label="工单状态筛选"><button className={status === 'active' ? 'selected' : ''} onClick={() => setStatus('active')}>进行中</button><button className={status === 'closed' ? 'selected' : ''} onClick={() => setStatus('closed')}>已关闭</button><button className={status === 'all' ? 'selected' : ''} onClick={() => setStatus('all')}>全部</button></div></section>
    {error && <div className="error-banner" role="alert">{error}</div>}<TicketList items={filtered} loading={loading} detailBase="/employee/tickets" emptyTitle="没有进行中的工单" /></div>
}
