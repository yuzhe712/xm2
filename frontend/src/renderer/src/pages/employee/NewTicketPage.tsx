import { FormEvent, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { useAuth } from '../../app/AuthProvider'
import { submitNewTicket } from '../../api/workflow'
import type { DeskId } from '../../types/tickets'

export function NewTicketPage(): JSX.Element {
  const auth = useAuth()
  const navigate = useNavigate()
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [desk, setDesk] = useState<DeskId>('support')
  const [priority, setPriority] = useState('P3')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (!auth.token) return
    setBusy(true); setError(null)
    try {
      const result = await submitNewTicket({ title: title.trim(), text: description.trim(), desk_id: desk, priority }, auth.token)
      navigate(`/employee/tickets/${result.ticket_id}`)
    } catch (caught) { setError(caught instanceof Error ? caught.message : '提交失败') }
    finally { setBusy(false) }
  }

  return <div className="narrow-page"><header className="page-header"><div><span className="eyebrow">员工门户</span><h1>新建工单</h1><p>描述实际影响和已尝试的操作，便于运维快速判断。</p></div></header>{error && <div className="error-banner" role="alert">{error}</div>}
    <form className="surface request-form" onSubmit={submit}><label><span>主题</span><input aria-label="工单主题" maxLength={200} value={title} onChange={(e) => setTitle(e.target.value)} placeholder="简要概括问题" /></label><label><span>详细描述</span><textarea aria-label="工单描述" rows={9} value={description} onChange={(e) => setDescription(e.target.value)} placeholder="发生了什么、影响范围、出现时间以及已尝试的操作" /></label><div className="form-grid two-columns"><label><span>服务台</span><select value={desk} onChange={(e) => setDesk(e.target.value as DeskId)}><option value="support">内部支持</option><option value="ops">IT 运维</option></select></label><label><span>紧急程度</span><select value={priority} onChange={(e) => setPriority(e.target.value)}><option value="P1">P1 紧急</option><option value="P2">P2 高</option><option value="P3">P3 常规</option><option value="P4">P4 低</option></select></label></div><div className="form-actions"><button type="button" className="button-secondary" onClick={() => navigate('/employee/tickets')}>取消</button><button type="submit" disabled={busy || !title.trim() || !description.trim()}>{busy ? '提交中...' : '提交工单'}</button></div></form></div>
}
