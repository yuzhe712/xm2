import { useEffect, useState } from 'react'
import { submitTicket, listMyTickets } from '../api/tickets'
import type {
  DeskId,
  TicketHistoryListResponse,
  TicketHistorySummary,
} from '../types/tickets'
import { TicketHistoryList } from './TicketHistoryList'

const DESKS: { id: DeskId; label: string; desc: string }[] = [
  { id: 'ops', label: 'IT 运维服务台', desc: '服务器、网络、数据库等运维类问题' },
  { id: 'support', label: '内部支持服务台', desc: '账号、权限、办公软件等日常支持类问题' },
]

const CATEGORIES: Record<DeskId, string[]> = {
  ops: ['告警/故障', '网络问题', '数据库问题', '发布/部署', '性能问题', '安全事件', '其他'],
  support: ['账号权限', '设备申请', '软件安装', '网络访问', '安全合规', '咨询/其他'],
}

interface Props {
  token: string
  userName: string
  onTicketSelect: (ticketId: string) => void
  refreshKey: number
}

export default function EmployeeDashboard({ token, userName, onTicketSelect, refreshKey }: Props) {
  const [deskId, setDeskId] = useState<DeskId>('ops')
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [category, setCategory] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [okResult, setOkResult] = useState<{ id: string; priority: string; reason: string } | null>(null)
  const [tickets, setTickets] = useState<TicketHistoryListResponse | null>(null)
  const [showTemplates, setShowTemplates] = useState(false)

  const cats = CATEGORIES[deskId]

  const loadTickets = async () => {
    try { const r = await listMyTickets(token, 50, 0, deskId); setTickets(r) } catch { /* */ }
  }

  useEffect(() => { void loadTickets() }, [refreshKey, deskId])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!title.trim() || !description.trim()) return
    setSubmitting(true)
    setError(null)
    setOkResult(null)
    const full = `【${category || cats[0]}】${title.trim()}\n\n${description.trim()}`
    try {
      const r = await submitTicket({ text: full, desk_id: deskId }, token)
      setOkResult({ id: r.ticket_id, priority: '', reason: '' })
      setTitle('')
      setDescription('')
      setCategory('')
      await loadTickets()
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '提交失败')
    } finally {
      setSubmitting(false)
    }
  }

  const fillTemplate = (tpl: string) => {
    setDescription((d) => (d ? d + '\n' + tpl : tpl))
    setShowTemplates(false)
  }

  const rows: TicketHistorySummary[] = tickets?.items ?? []

  return (
    <div className="emp-root">
      <div className="emp-main">
        <div className="emp-form-card">
          {/* Desk tabs */}
          <div className="emp-tabs">
            {DESKS.map((d) => (
              <button
                key={d.id}
                className={`emp-tab ${d.id === deskId ? 'emp-tab--on' : ''}`}
                onClick={() => { setDeskId(d.id); setCategory(''); setShowTemplates(false) }}
              >
                <strong>{d.label}</strong>
                <span>{d.desc}</span>
              </button>
            ))}
          </div>

          <form onSubmit={handleSubmit} className="emp-form">
            <div className="emp-row">
              <label className="emp-field flex-2">
                <span className="emp-label">标题</span>
                <input
                  className="emp-input"
                  type="text"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="一句话描述您遇到的问题"
                  maxLength={120}
                />
              </label>

              <label className="emp-field flex-1">
                <span className="emp-label">分类</span>
                <select
                  className="emp-input"
                  value={category}
                  onChange={(e) => setCategory(e.target.value)}
                >
                  <option value="">选择分类（可选）</option>
                  {cats.map((c) => <option key={c} value={c}>{c}</option>)}
                </select>
              </label>
            </div>

            <label className="emp-field">
              <div className="emp-label-row">
                <span className="emp-label">详细描述</span>
                <button
                  type="button"
                  className="emp-tpl-toggle"
                  onClick={() => setShowTemplates(!showTemplates)}
                >
                  {showTemplates ? '收起模板' : '📋 快捷模板'}
                </button>
              </div>
              <textarea
                className="emp-textarea"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder={`请描述：\n1. 什么时间开始出现问题？\n2. 具体表现是什么？（报错信息、截图等）\n3. 影响了哪些操作或系统？\n4. 是否尝试过什么解决方式？`}
                rows={6}
                maxLength={2000}
              />
              <span className="emp-count">{description.length}/2000</span>

              {showTemplates && (
                <div className="emp-tpl-panel">
                  {[
                    '无法访问内部系统，浏览器提示连接超时。',
                    '办公软件（如邮件、文档）无法正常使用。',
                    '需要为新同事开通以下系统权限：1) 2) 3)',
                    '电脑运行缓慢，风扇噪音大，疑似硬件问题。',
                    '收到异常登录提醒，怀疑账号被盗用。',
                  ].map((tpl, i) => (
                    <button
                      key={i}
                      type="button"
                      className="emp-tpl-chip"
                      onClick={() => fillTemplate(tpl)}
                    >
                      {tpl}
                    </button>
                  ))}
                </div>
              )}
            </label>

            <div className="emp-actions">
              <button className="button-primary" type="submit" disabled={submitting || !title.trim() || !description.trim()}>
                {submitting ? '提交中...' : '提交工单'}
              </button>
              {error && <span className="emp-err">{error}</span>}
              {okResult && (
                <span className="emp-ok">
                  已提交 {okResult.id}，运维人员将尽快处理
                </span>
              )}
              <span className="emp-hint">{userName}，提交后可在下方「我的工单」中跟踪处理进度</span>
            </div>
          </form>
        </div>

        <div className="emp-list-card">
          <TicketHistoryList
            items={rows}
            loading={false}
            total={rows.length}
            onSelect={onTicketSelect}
            title="我的工单"
            emptyText="还没有提交过工单，上方表单提交后这里会显示处理进度。"
          />
        </div>
      </div>
    </div>
  )
}
