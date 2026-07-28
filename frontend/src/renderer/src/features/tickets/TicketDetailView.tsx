import { ArrowLeft, CheckCircle2, Download, MessageSquare, Paperclip, RotateCcw, Send, Upload, UserRoundCheck, XCircle } from 'lucide-react'
import { FormEvent, useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { useAuth } from '../../app/AuthProvider'
import { ApiClientError } from '../../api/client'
import {
  acceptTicket, addComment, cancelTicket, claimTicket, confirmTicket, decideAiRun, downloadAttachment,
  getAiRun, getComments, getTicketRecord, getTimeline, getWorkflowTicket, listAttachments,
  reopenTicket, rerunAi, resolveTicket, uploadAttachment,
} from '../../api/workflow'
import type { AiRun, CommentVisibility, TicketAttachment, TicketComment, TicketEvent, TicketDetailRecord, UserRole, WorkflowTicket } from '../../types/workflow'
import { AiSuggestionPanel } from './AiSuggestionPanel'
import { formatDate, isOverdue, statusLabels } from './ticketPresentation'

const eventLabels: Record<string, string> = {
  ticket_created: '工单已创建', ai_triage_queued: 'AI 分析已排队', ai_triage_started: 'AI 分析已开始',
  ai_triage_completed: 'AI 分析已完成', ai_triage_failed: 'AI 分析失败', triage_completed: '工单已受理',
  ticket_claimed: '工单已认领', ticket_assigned: '工单已转派', comment_added: '添加公开回复',
  internal_note_added: '添加内部备注', ticket_resolved: '工单已解决', ticket_closed: '提交人确认关闭',
  ticket_reopened: '工单已重新打开', ticket_cancelled: '工单已取消', ai_rerun_queued: 'AI 重新分析已排队',
  attachment_uploaded: '上传附件',
}

function formatBytes(size: number): string {
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / (1024 * 1024)).toFixed(1)} MB`
}

export function TicketDetailView({ ticketId, role, backTo }: { ticketId: string; role: UserRole; backTo: string }): JSX.Element {
  const auth = useAuth()
  const [ticket, setTicket] = useState<WorkflowTicket | null>(null)
  const [record, setRecord] = useState<TicketDetailRecord | null>(null)
  const [comments, setComments] = useState<TicketComment[]>([])
  const [timeline, setTimeline] = useState<TicketEvent[]>([])
  const [aiRun, setAiRun] = useState<AiRun | null>(null)
  const [attachments, setAttachments] = useState<TicketAttachment[]>([])
  const [attachmentFile, setAttachmentFile] = useState<File | null>(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [comment, setComment] = useState('')
  const [visibility, setVisibility] = useState<CommentVisibility>('public')
  const [reason, setReason] = useState('')
  const [triage, setTriage] = useState({ category: 'service_request', priority: 'P3', service: '' })
  const [resolution, setResolution] = useState({ resolution_summary: '', root_cause: '', fix_action: '', verification: '' })

  const load = useCallback(async () => {
    if (!auth.token) return
    setLoading(true)
    setError(null)
    try {
      const [workflow, commentItems, eventItems, detail, attachmentItems] = await Promise.all([
        getWorkflowTicket(ticketId, auth.token), getComments(ticketId, auth.token),
        getTimeline(ticketId, auth.token), getTicketRecord(ticketId, auth.token).catch(() => null),
        listAttachments(ticketId, auth.token),
      ])
      setTicket(workflow)
      setComments(commentItems)
      setTimeline(eventItems)
      setRecord(detail)
      setAttachments(attachmentItems)
      const runId = detail?.ai_run_id
      if (runId && role !== 'employee') {
        const persistedRun = await getAiRun(runId, auth.token).catch(() => null)
        setAiRun(persistedRun ?? {
          id: runId,
          ticket_id: ticketId,
          status: (detail?.ai_status ?? 'failed') as AiRun['status'],
          stage: detail?.ai_status ?? 'unknown',
          progress: detail?.ai_status === 'completed' ? 100 : 0,
          pipeline_version: 'unknown', provider: 'unknown', model: 'unknown',
          prompt_version: 'unknown', result: detail?.ai_result ?? null, evidence: [],
          confidence: null, error_code: null, error_message: null, duration_ms: null,
          decision: null, retry_count: 0, created_at: workflow.created_at,
          updated_at: workflow.updated_at,
        })
      } else setAiRun(null)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '无法加载工单')
    } finally {
      setLoading(false)
    }
  }, [auth.token, role, ticketId])

  useEffect(() => { void load() }, [load])

  const perform = async (action: () => Promise<unknown>) => {
    setBusy(true)
    setError(null)
    try { await action(); await load() }
    catch (caught) {
      if (caught instanceof ApiClientError && caught.code === 'TICKET_VERSION_CONFLICT') {
        setError('工单已被他人更新，页面已刷新，请重新确认后操作。')
        await load()
      } else setError(caught instanceof Error ? caught.message : '操作失败')
    } finally { setBusy(false) }
  }

  const submitComment = (event: FormEvent) => {
    event.preventDefault()
    if (!ticket || !auth.token || !comment.trim()) return
    void perform(() => addComment(ticketId, ticket.version, comment, visibility, auth.token!)).then(() => setComment(''))
  }

  const saveAttachment = () => {
    if (!attachmentFile || !auth.token) return
    void perform(() => uploadAttachment(ticketId, attachmentFile, auth.token!))
      .then(() => setAttachmentFile(null))
  }

  const saveDownload = async (attachment: TicketAttachment) => {
    if (!auth.token) return
    setError(null)
    try {
      const blob = await downloadAttachment(ticketId, attachment.id, auth.token)
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = attachment.original_name
      anchor.click()
      URL.revokeObjectURL(url)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '附件下载失败')
    }
  }

  if (loading && !ticket) return <div className="loading-panel">正在加载工单详情...</div>
  if (!ticket) return <div className="error-state"><strong>无法打开工单</strong><span>{error ?? '工单不存在或无权访问。'}</span><Link to={backTo}>返回列表</Link></div>

  const canOperate = role === 'operator' || role === 'admin'
  const canResolve = ticket.status === 'in_progress' && (role === 'admin' || ticket.assignee_id === auth.user?.id)

  return (
    <div className="detail-page">
      <header className="detail-header">
        <Link className="back-link" to={backTo}><ArrowLeft size={17} />返回列表</Link>
        <div className="detail-title-row"><div><span className="eyebrow">{ticket.ticket_id}</span><h1>{ticket.title}</h1></div><span className={`status-badge status-${ticket.status}`}>{statusLabels[ticket.status]}</span></div>
      </header>
      {error && <div className="error-banner" role="alert">{error}</div>}
      <div className={canOperate ? 'detail-layout with-ai' : 'detail-layout'}>
        <div className="detail-main">
          <section className="surface ticket-overview">
            <div className="section-heading"><h2>工单概览</h2></div>
            <p className="ticket-description">{ticket.description}</p>
            <dl className="fact-grid overview-facts">
              <div><dt>提交人</dt><dd>{ticket.submitter}</dd></div><div><dt>优先级</dt><dd>{ticket.priority ?? 'P3'}</dd></div>
              <div><dt>服务台</dt><dd>{ticket.desk_id === 'ops' ? 'IT 运维' : '内部支持'}</dd></div><div><dt>处理人</dt><dd>{ticket.claimed_by ?? '未分配'}</dd></div>
              <div><dt>响应时限</dt><dd className={isOverdue(ticket.response_due_at) && !ticket.first_responded_at ? 'sla-overdue' : ''}>{formatDate(ticket.response_due_at)}</dd></div>
              <div><dt>解决时限</dt><dd className={isOverdue(ticket.resolution_due_at) && !['resolved', 'closed'].includes(ticket.status) ? 'sla-overdue' : ''}>{formatDate(ticket.resolution_due_at)}</dd></div>
            </dl>
          </section>

          <section className="surface attachment-section">
            <div className="section-heading"><div><Paperclip size={18} /><h2>附件</h2></div><span>{attachments.length} 个</span></div>
            <div className="attachment-list">{attachments.length ? attachments.map((attachment) => <article key={attachment.id}><div><strong>{attachment.original_name}</strong><span>{formatBytes(attachment.size_bytes)} · {formatDate(attachment.created_at)}</span></div><button className="button-quiet" type="button" title="下载附件" onClick={() => void saveDownload(attachment)}><Download size={15} />下载</button></article>) : <p className="muted">暂无附件。</p>}</div>
            <div className="attachment-upload"><input aria-label="选择附件" type="file" accept=".txt,.log,.pdf,.png,.jpg,.jpeg" onChange={(event) => setAttachmentFile(event.target.files?.[0] ?? null)} /><button type="button" disabled={busy || !attachmentFile} onClick={saveAttachment}><Upload size={16} />上传</button></div>
          </section>

          {canOperate && (ticket.status === 'pending' || ticket.status === 'open') && <section className="surface action-strip">
            <div><strong>受理操作</strong><span>AI 不可用时可直接人工受理或认领。</span></div>
            {ticket.status === 'pending' && <details><summary>人工受理</summary><div className="compact-form"><input aria-label="工单分类" value={triage.category} onChange={(e) => setTriage({ ...triage, category: e.target.value })} /><select aria-label="受理优先级" value={triage.priority} onChange={(e) => setTriage({ ...triage, priority: e.target.value })}><option>P1</option><option>P2</option><option>P3</option><option>P4</option></select><input aria-label="受影响服务" value={triage.service} onChange={(e) => setTriage({ ...triage, service: e.target.value })} placeholder="受影响服务（可选）" /><button type="button" disabled={busy} onClick={() => void perform(() => acceptTicket(ticketId, ticket.version, triage.category, triage.priority, triage.service, auth.token!))}>确认受理</button></div></details>}
            <button type="button" disabled={busy} onClick={() => void perform(() => claimTicket(ticketId, ticket.version, auth.token!))}><UserRoundCheck size={17} />认领工单</button>
          </section>}

          <section className="surface conversation-section">
            <div className="section-heading"><h2>沟通记录</h2><span>{comments.length} 条</span></div>
            <div className="comment-list">{comments.length ? comments.map((item) => <article className={`comment comment-${item.visibility}`} key={item.id}><div><strong>{item.author}</strong><span>{item.visibility === 'internal' ? '内部备注' : '公开回复'} · {formatDate(item.created_at)}</span></div><p>{item.body}</p></article>) : <p className="muted">尚无沟通记录。</p>}</div>
            <form className="comment-form" onSubmit={submitComment}>
              <label><span>{visibility === 'internal' ? '内部备注' : '公开回复'}</span><textarea aria-label="评论内容" value={comment} onChange={(e) => setComment(e.target.value)} rows={3} placeholder="输入处理进展或需要补充的信息" /></label>
              <div>{canOperate && <select aria-label="评论可见范围" value={visibility} onChange={(e) => setVisibility(e.target.value as CommentVisibility)}><option value="public">公开回复</option><option value="internal">内部备注</option></select>}<button type="submit" disabled={busy || !comment.trim()}><Send size={16} />发送</button></div>
            </form>
          </section>

          {canResolve && <section className="surface resolution-form"><div className="section-heading"><h2>解决工单</h2></div><div className="form-grid two-columns"><label><span>解决摘要</span><textarea value={resolution.resolution_summary} onChange={(e) => setResolution({ ...resolution, resolution_summary: e.target.value })} /></label><label><span>根因</span><textarea value={resolution.root_cause} onChange={(e) => setResolution({ ...resolution, root_cause: e.target.value })} /></label><label><span>修复动作</span><textarea value={resolution.fix_action} onChange={(e) => setResolution({ ...resolution, fix_action: e.target.value })} /></label><label><span>验证结果</span><textarea value={resolution.verification} onChange={(e) => setResolution({ ...resolution, verification: e.target.value })} /></label></div><button type="button" disabled={busy || Object.values(resolution).some((value) => !value.trim())} onClick={() => void perform(() => resolveTicket(ticketId, ticket.version, resolution, auth.token!))}><CheckCircle2 size={17} />标记已解决</button></section>}

          {role === 'employee' && ticket.status === 'resolved' && <section className="surface confirmation-panel"><div><CheckCircle2 size={22} /><div><strong>运维已提交解决结果</strong><span>{ticket.resolution_summary}</span></div></div><button type="button" disabled={busy} onClick={() => void perform(() => confirmTicket(ticketId, ticket.version, auth.token!))}>确认关闭</button></section>}

          {role === 'employee' && (ticket.status === 'resolved' || ticket.status === 'closed') && <section className="surface secondary-action"><div><RotateCcw size={20} /><div><strong>问题仍未解决？</strong><span>说明原因后重新打开工单。</span></div></div><input aria-label="重新打开原因" value={reason} onChange={(e) => setReason(e.target.value)} placeholder="重新打开原因" /><button type="button" disabled={busy || !reason.trim()} onClick={() => void perform(() => reopenTicket(ticketId, ticket.version, reason, auth.token!))}>重新打开</button></section>}

          {role === 'employee' && (ticket.status === 'pending' || ticket.status === 'open') && <section className="surface secondary-action"><div><XCircle size={20} /><div><strong>取消工单</strong><span>仅可取消尚未开始处理的工单。</span></div></div><input aria-label="取消原因" value={reason} onChange={(e) => setReason(e.target.value)} placeholder="取消原因" /><button className="button-danger" type="button" disabled={busy || !reason.trim()} onClick={() => void perform(() => cancelTicket(ticketId, ticket.version, reason, auth.token!))}>取消</button></section>}

          <section className="surface timeline-section"><div className="section-heading"><div><MessageSquare size={18} /><h2>处理时间线</h2></div></div><ol className="timeline">{timeline.map((event) => <li key={event.id}><span className="timeline-dot" /><div><strong>{eventLabels[event.event_type] ?? event.event_type}</strong><span>{event.actor ?? '系统'} · {formatDate(event.created_at)}</span></div></li>)}</ol></section>
        </div>
        {canOperate && <AiSuggestionPanel run={aiRun} loading={busy} onRerun={() => void perform(async () => { setAiRun(await rerunAi(ticketId, auth.token!)) })} onDecision={(decision, note, modifiedResult) => { if (aiRun) void perform(() => decideAiRun(aiRun.id, decision, note, modifiedResult, auth.token!)) }} />}
      </div>
      {record?.data_mode === 'mock' && <span className="sr-only">当前环境数据模式由后端配置为 mock</span>}
    </div>
  )
}
