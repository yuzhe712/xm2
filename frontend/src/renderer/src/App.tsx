import { useEffect, useMemo, useState } from 'react'

import { AgentTimeline } from './components/AgentTimeline'
import { BackendConnectionPanel } from './components/BackendConnectionPanel'
import { ClassificationPanel } from './components/ClassificationPanel'
import { ContextPanel } from './components/ContextPanel'
import { DiagnosisPanel } from './components/DiagnosisPanel'
import EmployeeDashboard from './components/EmployeeDashboard'
import { ErrorPanel } from './components/ErrorPanel'
import { EvidencePanel } from './components/EvidencePanel'
import LoginPage from './components/LoginPage'
import { MockDataBadge } from './components/MockDataBadge'
import NotificationStatus from './components/NotificationStatus'
import ResolveTicketPanel from './components/ResolveTicketPanel'
import { ReviewerPanel } from './components/ReviewerPanel'
import { ProcessingControls } from './components/ProcessingControls'
import { ResultReport } from './components/ResultReport'
import { RoutingPanel } from './components/RoutingPanel'
import { SupportReplyPanel } from './components/SupportReplyPanel'
import { TicketHistoryList } from './components/TicketHistoryList'
import { TicketInputPanel } from './components/TicketInputPanel'
import { TicketRunDetailPanel } from './components/TicketRunDetailPanel'
import { apiBaseUrl } from './config/backend'
import { sampleTickets } from './data/sampleTickets'
import { useAuth } from './hooks/useAuth'
import { useDeskResources } from './hooks/useDeskResources'
import { useTicketHistory } from './hooks/useTicketHistory'
import { useTicketProcessing } from './hooks/useTicketProcessing'
import type { DataMode, DeskId, RunStatus, SupportReplyDraftUpdateRequest, TicketHistorySummary, TicketLifecycleUpdateRequest, TicketStatus } from './types/tickets'

const BACKEND_URL_STORAGE_KEY = 'intelliticket.backendUrl'
const sampleTicket = sampleTickets[0]

const MODE_LABELS: Record<string, string> = {
  idle: '待处理',
  'rest-loading': 'REST 同步处理中',
  'ws-connecting': 'WebSocket 连接中',
  'ws-running': 'WebSocket 实时处理中',
  cancelling: '取消请求已发送',
  completed: '处理完成',
  error: '处理失败',
  cancelled: '已取消',
}

const STATUS_LABELS: Record<RunStatus, string> = {
  queued: 'AI 排队中',
  running: 'AI 分析中',
  completed: '已完成',
  failed: '失败',
  cancelled: '已取消',
  pending: '待处理',
}

const TICKET_STATUS_LABELS: Record<TicketStatus, string> = {
  pending: '待处理',
  open: '待处理',
  in_progress: '处理中',
  resolved: '已解决',
  closed: '已关闭',
  cancelled: '已取消',
}

const INTERNAL_MODULE_TABS = [
  '服务目录',
  '请求',
  '智能处理',
  '知识库',
  '报表',
  '设置',
] as const
type InternalModuleTab = (typeof INTERNAL_MODULE_TABS)[number]
type ModuleTab = '首页' | InternalModuleTab
type PortalKey = 'ops' | 'support'
type RequestView = 'all' | 'unresolved' | 'completed' | 'cancelled'
type UserRole = 'operator' | 'employee'
type StatusFilter = 'all' | RunStatus
type PriorityFilter = 'all' | 'P1' | 'P2' | 'P3' | 'unknown'
type SortKey = 'updated_at' | 'created_at' | 'ticket_status'

const SORT_OPTIONS: Array<{ key: SortKey; label: string }> = [
  { key: 'updated_at', label: '更新时间 ↓' },
  { key: 'created_at', label: '创建时间 ↓' },
  { key: 'ticket_status', label: '工单状态' },
]

const STATUS_SORT_ORDER: Record<string, number> = {
  pending: 0, open: 1, in_progress: 2, resolved: 3, closed: 4, cancelled: 5,
}

const REQUEST_VIEWS: Array<{ key: RequestView; label: string }> = [
  { key: 'all', label: '所有请求' },
  { key: 'unresolved', label: '未解决' },
  { key: 'completed', label: '已完成' },
  { key: 'cancelled', label: '已取消' },
]

const PORTAL_CONFIG: Record<
  PortalKey,
  {
    title: string
    mark: string
    subtitle: string
    examples: string
    tabs: InternalModuleTab[]
  }
> = {
  ops: {
    title: 'IT Helpdesk / IT 运维服务台',
    mark: 'IT',
    subtitle: '处理生产系统告警、服务故障、性能异常和变更影响。',
    examples: '示例：支付服务超时、数据库连接池耗尽、接口 5xx、发布后异常。',
    tabs: ['服务目录', '请求', '智能处理', '知识库', '报表', '设置'],
  },
  support: {
    title: '基础设施 / 内部支持服务台',
    mark: 'IS',
    subtitle: '处理员工账号、权限申请、VPN、办公网和内部系统访问问题。',
    examples: '示例：申请监控权限、VPN 连不上、打不开内部系统、新员工账号问题。',
    tabs: ['服务目录', '请求', '智能处理', '知识库', '报表', '设置'],
  },
}

function storedBackendUrl(): string {
  const stored = localStorage.getItem(BACKEND_URL_STORAGE_KEY)
  if (!stored) return apiBaseUrl
  try {
    const url = new URL(stored)
    if (url.protocol === 'http:' || url.protocol === 'https:') return stored
  } catch {
    return apiBaseUrl
  }
  return apiBaseUrl
}

function matchesRequestView(item: TicketHistorySummary, view: RequestView): boolean {
  if (view === 'all') return true
  if (view === 'unresolved') return item.ticket_status === 'pending' || item.ticket_status === 'open' || item.ticket_status === 'in_progress'
  if (view === 'completed') return item.ticket_status === 'resolved' || item.ticket_status === 'closed'
  return item.ticket_status === 'cancelled'
}

function matchesPriority(item: TicketHistorySummary, priority: PriorityFilter): boolean {
  if (priority === 'all') return true
  if (priority === 'unknown') return !item.priority
  return item.priority === priority
}

function dominantDataMode(modes: DataMode[]): DataMode {
  if (modes.includes('real')) return 'real'
  if (modes.includes('demo')) return 'demo'
  return 'mock'
}

function sourceNotice(mode: DataMode, realText: string, mockText: string): string {
  return mode === 'real' ? realText : mockText
}

export function App(): JSX.Element {
  const auth = useAuth()

  const [activeModule, setActiveModule] = useState<ModuleTab>('首页')
  const [ticketText, setTicketText] = useState(sampleTicket.text)
  const [selectedEvidenceId, setSelectedEvidenceId] = useState<string | null>(null)
  const [activeApiBaseUrl, setActiveApiBaseUrl] = useState(storedBackendUrl)
  const [requestView, setRequestView] = useState<RequestView>('all')
  const [requestQuery, setRequestQuery] = useState('')
  const [requestStatusFilter, setRequestStatusFilter] = useState<StatusFilter>('all')
  const [requestPriorityFilter, setRequestPriorityFilter] = useState<PriorityFilter>('all')
  const [requestSort, setRequestSort] = useState<SortKey>('updated_at')
  const [selectedTicketId, setSelectedTicketId] = useState<string | null>(null)
  const [reprocessTargetTicketId, setReprocessTargetTicketId] = useState<string | null>(null)
  const [activePortal, setActivePortal] = useState<PortalKey>('ops')
  const [processingDeskId, setProcessingDeskId] = useState<DeskId>('ops')
  const activeDeskId: DeskId = activePortal === 'support' ? 'support' : 'ops'
  const processing = useTicketProcessing({ apiBaseUrl: activeApiBaseUrl, token: auth.auth?.token })
  const history = useTicketHistory({ apiBaseUrl: activeApiBaseUrl, deskId: activeDeskId, token: auth.auth?.token })
  const deskResources = useDeskResources({ apiBaseUrl: activeApiBaseUrl, deskId: activeDeskId })
  const { error: historyError, items, loading, refresh, selectTicket, total } = history

  useEffect(() => {
    localStorage.setItem(BACKEND_URL_STORAGE_KEY, activeApiBaseUrl)
  }, [activeApiBaseUrl])

  useEffect(() => {
    if (processing.mode === 'completed' && processing.result) {
      void refresh()
    }
  }, [refresh, processing.mode, processing.result])

  useEffect(() => {
    if (auth.isOperator) {
      void refresh()
    }
  }, [auth.isOperator, refresh])

  const modeLabel = MODE_LABELS[processing.mode] ?? processing.mode
  const currentClassification =
    processing.result?.classification ?? processing.historyDetail?.latest_run?.response?.classification
  const isSupportResult = currentClassification?.category === 'support_request'
  const canSubmit = useMemo(
    () => ticketText.trim().length > 0 && !processing.isBusy,
    [processing.isBusy, ticketText],
  )
  const visibleEvidence = processing.result?.evidence ?? processing.historyDetail?.latest_run?.evidence ?? []
  const activePortalConfig = PORTAL_CONFIG[activePortal]
  const catalogDataMode = dominantDataMode(deskResources.catalogItems.map((item) => item.data_mode))
  const knowledgeDataMode = dominantDataMode(deskResources.knowledgeItems.map((item) => item.data_mode))
  const globalDataMode = dominantDataMode([
    ...deskResources.catalogItems.map((item) => item.data_mode),
    ...deskResources.knowledgeItems.map((item) => item.data_mode),
    ...visibleEvidence.map((item) => item.data_mode),
  ])

  const statusCounts = useMemo(
    () => ({
      completed: items.filter((item) => item.status === 'completed').length,
      unresolved: items.filter(
        (item) => item.ticket_status === 'pending' || item.ticket_status === 'open' || item.ticket_status === 'in_progress',
      ).length,
      resolved: items.filter(
        (item) => item.ticket_status === 'resolved' || item.ticket_status === 'closed',
      ).length,
      cancelled: items.filter((item) => item.ticket_status === 'cancelled').length,
      p1: items.filter((item) => item.priority === 'P1').length,
      payment: items.filter((item) => item.affected_service === 'payment-service').length,
    }),
    [items],
  )

  const filteredItems = useMemo(() => {
    const query = requestQuery.trim().toLowerCase()
    const result = items.filter((item) => {
      if (!matchesRequestView(item, requestView)) return false
      if (requestStatusFilter !== 'all' && item.status !== requestStatusFilter) return false
      if (!matchesPriority(item, requestPriorityFilter)) return false
      if (!query) return true
      return [item.ticket_id, item.summary, item.report_title, item.affected_service]
        .filter(Boolean)
        .some((value) => value?.toLowerCase().includes(query))
    })
    return [...result].sort((a, b) => {
      if (requestSort === 'ticket_status') {
        const sa = STATUS_SORT_ORDER[a.ticket_status] ?? 99
        const sb = STATUS_SORT_ORDER[b.ticket_status] ?? 99
        if (sa !== sb) return sa - sb
        return (a.updated_at ?? '').localeCompare(b.updated_at ?? '')
      }
      const va = requestSort === 'created_at' ? (a.created_at ?? '') : (a.updated_at ?? '')
      const vb = requestSort === 'created_at' ? (b.created_at ?? '') : (b.updated_at ?? '')
      // 新的排前面：va (新) < vb (旧) → 返回正数，a 排后面 → b (旧) 排前面
      if (va > vb) return -1
      if (va < vb) return 1
      return 0
    })
  }, [items, requestPriorityFilter, requestQuery, requestSort, requestStatusFilter, requestView])

  function startNewRequest(template = '', deskId: DeskId = activeDeskId): void {
    setReprocessTargetTicketId(null)
    setProcessingDeskId(deskId)
    setTicketText(template)
    setActiveModule('智能处理')
  }

  function enterOperationsDesk(): void {
    setActivePortal('ops')
    setProcessingDeskId('ops')
    setRequestView('unresolved')
    setRequestStatusFilter('all')
    setActiveModule('请求')
  }

  function enterSupportDesk(): void {
    setActivePortal('support')
    setProcessingDeskId('support')
    setActiveModule('服务目录')
  }

  function handleSelectTicket(ticketId: string): void {
    setSelectedTicketId(ticketId)
    void selectTicket(ticketId).then((detail) => {
      if (detail) {
        processing.showPersistedDetail(detail)
        setSelectedEvidenceId(null)
      }
    })
  }

  function handleEmployeeSelectTicket(ticketId: string): void {
    setSelectedTicketId(ticketId)
    void selectTicket(ticketId).then((detail) => {
      if (detail) {
        processing.showPersistedDetail(detail)
      }
    })
  }

  function handleUpdateLifecycle(update: TicketLifecycleUpdateRequest): void {
    if (!processing.historyDetail) return
    void history.updateLifecycle(processing.historyDetail.ticket_id, update).then((detail) => {
      if (detail) {
        processing.showPersistedDetail(detail)
        setSelectedEvidenceId(null)
      }
    })
  }

  function handleResolveTicket(rootCause: string, fixAction: string, verification: string): void {
    handleUpdateLifecycle({
      ticket_status: 'resolved',
      root_cause: rootCause,
      fix_action: fixAction,
      verification: verification,
    })
  }

  function handleUpdateSupportReplyDraft(update: SupportReplyDraftUpdateRequest): void {
    const ticketId = processing.historyDetail?.ticket_id ?? processing.result?.ticket_id
    if (!ticketId) return
    void history.updateSupportDraft(ticketId, update).then((detail) => {
      if (detail) {
        processing.showPersistedDetail(detail)
      }
    })
  }

  const handleReprocessSelectedTicket = (): void => {
    if (!processing.historyDetail) return
    setReprocessTargetTicketId(processing.historyDetail.ticket_id)
    setProcessingDeskId(processing.historyDetail.desk_id)
    setTicketText(processing.historyDetail.input_text)
    setActiveModule('智能处理')
  }

  function handleRunReprocessPreview(): void {
    if (!reprocessTargetTicketId) return
    void processing.runReprocessPreview(reprocessTargetTicketId)
  }

  function handleSaveReprocessResult(): void {
    if (!reprocessTargetTicketId) return
    void history.reprocess(reprocessTargetTicketId).then((detail) => {
      if (detail) {
        processing.showPersistedDetail(detail)
        setSelectedEvidenceId(null)
        setSelectedTicketId(detail.ticket_id)
        setReprocessTargetTicketId(null)
        setActiveModule('请求')
      }
    })
  }

  const requestFilters = (
    <section className="panel request-toolbar" aria-label="请求筛选">
      <div className="panel-heading-row">
        <div>
          <h2>所有未解决的请求</h2>
          <p className="muted">筛选和视图基于当前加载的历史请求；未解决对应待处理或处理中工单。</p>
        </div>
        <button type="button" onClick={() => startNewRequest('')}>
          新建请求
        </button>
      </div>
      <div className="request-view-tabs" role="tablist" aria-label="请求视图">
        {REQUEST_VIEWS.map((view) => (
          <button
            key={view.key}
            type="button"
            className={view.key === requestView ? 'view-tab view-tab-active' : 'view-tab'}
            aria-selected={view.key === requestView}
            onClick={() => setRequestView(view.key)}
          >
            {view.label}
          </button>
        ))}
      </div>
      <div className="filter-grid">
        <label>
          <span>搜索</span>
          <input
            aria-label="搜索请求"
            value={requestQuery}
            onChange={(event) => setRequestQuery(event.target.value)}
            placeholder="工单号 / 主题 / 服务"
          />
        </label>
        <label>
          <span>状态</span>
          <select
            aria-label="状态筛选"
            value={requestStatusFilter}
            onChange={(event) => setRequestStatusFilter(event.target.value as StatusFilter)}
          >
            <option value="all">全部</option>
            <option value="completed">已完成</option>
            <option value="failed">失败</option>
            <option value="cancelled">已取消</option>
          </select>
        </label>
        <label>
          <span>优先级</span>
          <select
            aria-label="优先级筛选"
            value={requestPriorityFilter}
            onChange={(event) => setRequestPriorityFilter(event.target.value as PriorityFilter)}
          >
            <option value="all">全部</option>
            <option value="P1">P1</option>
            <option value="P2">P2</option>
            <option value="P3">P3</option>
            <option value="unknown">未知</option>
          </select>
        </label>
        <label>
          <span>排序</span>
          <select
            aria-label="排序方式"
            value={requestSort}
            onChange={(event) => setRequestSort(event.target.value as SortKey)}
          >
            {SORT_OPTIONS.map((opt) => (
              <option key={opt.key} value={opt.key}>{opt.label}</option>
            ))}
          </select>
        </label>
      </div>
    </section>
  )

  const requestList = (
    <section className="requests-pane" aria-label="请求列表">
      {requestFilters}
      <TicketHistoryList
        title="请求列表"
        emptyText="当前筛选条件下暂无请求。"
        items={filteredItems}
        loading={loading}
        total={filteredItems.length}
        selectedTicketId={selectedTicketId}
        onSelect={handleSelectTicket}
      />
      <ErrorPanel error={historyError} />
    </section>
  )

  const serviceCatalogPage = (
    <div className="module-page catalog-page">
      <section className="panel catalog-hero">
        <div className="panel-heading-row">
          <div>
            <h1>{activeDeskId === 'support' ? '内部支持服务目录' : '服务目录'}</h1>
            <p className="muted">查看当前服务台覆盖的问题类型和处理范围；提交请求请进入“请求”或“智能处理”。</p>
          </div>
          <MockDataBadge mode={catalogDataMode} />
        </div>
        <p className="notice">
          {sourceNotice(
            catalogDataMode,
            '当前目录包含后端返回的真实数据；目录项仍需按来源和证据质量复核。',
            '当前目录来自本地 mock 服务目录，仅说明服务范围，未接入真实 ITSM 服务目录或审批流。',
          )}
        </p>
      </section>
      <ErrorPanel error={deskResources.error} />
      {deskResources.loading && <p className="muted">正在加载服务目录...</p>}
      {!deskResources.loading && deskResources.catalogItems.length === 0 && !deskResources.error && (
        <section className="panel"><p className="muted">该服务台暂无服务目录。</p></section>
      )}
      <section className="catalog-grid" aria-label="服务目录">
        {deskResources.catalogItems.map((item) => (
          <article className="panel catalog-card" key={item.id}>
            <div className="catalog-card-header">
              <span className="badge badge-priority">{item.category}</span>
              <span className="priority-chip">{item.priority_hint}</span>
            </div>
            <h2>{item.title}</h2>
            <p className="muted">{item.description}</p>
            <dl className="details-grid compact">
              <dt>服务</dt>
              <dd>{item.affected_service}</dd>
              <dt>数据</dt>
              <dd><MockDataBadge mode={item.data_mode} /></dd>
            </dl>
          </article>
        ))}
      </section>
    </div>
  )

  const ticketWork = (
    <section className="ticket-work-pane" aria-label="智能处理工作区">
      <section className="panel service-catalog-panel">
        <div className="panel-heading-row">
          <div>
            <h2>智能处理工作区</h2>
            <p className="muted">
              当前按 {processingDeskId === 'support' ? '内部支持服务台' : 'IT 运维服务台'} 处理；
              可手动输入请求，或从“请求”列表中选择历史工单后重新处理。
            </p>
          </div>
        </div>
      </section>
      <TicketInputPanel
        value={ticketText}
        disabled={processing.isBusy}
        onChange={setTicketText}
      />
      <ProcessingControls
        canSubmit={canSubmit}
        canCancel={processing.canCancel}
        modeLabel={modeLabel}
        onRest={() => {
          if (reprocessTargetTicketId) {
            handleRunReprocessPreview()
            return
          }
          void processing.runRest(ticketText, processingDeskId)
        }}
        onWebSocket={() => processing.runWebSocket(ticketText, processingDeskId)}
        onCancel={processing.cancelWebSocket}
      />
      {reprocessTargetTicketId && (
        <section className="panel">
          <h3>重新处理预览</h3>
          <p className="notice">
            当前正在预览重新处理 {reprocessTargetTicketId}；预览结果不会写入历史，确认后请点击“保存到原工单”。
          </p>
          <div className="button-row compact-buttons">
            <button type="button" disabled={!processing.result || history.loading} onClick={handleSaveReprocessResult}>
              保存到原工单
            </button>
            <button type="button" onClick={() => setReprocessTargetTicketId(null)}>
              退出重新处理
            </button>
          </div>
        </section>
      )}
      <TicketRunDetailPanel detail={processing.historyDetail} />
      <ErrorPanel error={processing.error} />
      {isSupportResult ? (
        <SupportReplyPanel
          report={processing.result?.report}
          routing={processing.result?.routing}
          supportResult={processing.result?.support_result}
          draft={processing.historyDetail?.support_reply_draft}
          saving={history.loading}
          onSaveDraft={handleUpdateSupportReplyDraft}
          onEvidenceSelect={setSelectedEvidenceId}
        />
      ) : (
        <ResultReport report={processing.result?.report} />
      )}
      {processing.result?.notification ? (
        <NotificationStatus notification={processing.result.notification as Record<string, unknown>} />
      ) : null}
    </section>
  )

  const inspector = (
    <aside className="inspector-pane" aria-label="AI 调查与证据">
      <AgentTimeline
        events={processing.events}
        trace={processing.restTrace}
        storedRuns={processing.storedAgentRuns}
        cancelExplanation={processing.cancelExplanation}
        onEvidenceSelect={setSelectedEvidenceId}
      />
      <EvidencePanel
        evidence={visibleEvidence}
        selectedEvidenceId={selectedEvidenceId}
        onSelectEvidence={setSelectedEvidenceId}
      />
      <ClassificationPanel
        classification={processing.result?.classification}
        onEvidenceSelect={setSelectedEvidenceId}
      />
      <ContextPanel context={processing.result?.context} />
      {!isSupportResult && (
        <>
          <DiagnosisPanel
            diagnosis={processing.result?.diagnosis}
            onEvidenceSelect={setSelectedEvidenceId}
          />
          <RoutingPanel
            routing={processing.result?.routing}
            onEvidenceSelect={setSelectedEvidenceId}
          />
          <ReviewerPanel
            review={processing.result?.review}
            onEvidenceSelect={setSelectedEvidenceId}
          />
        </>
      )}
    </aside>
  )

  const requestDetailDrawer = (
    <aside className="request-detail-drawer" aria-label="请求详情抽屉">
      {!processing.historyDetail && (
        <section className="panel empty-module-panel">
          <h2>请求详情</h2>
          <p className="muted">从左侧请求列表选择一条工单，查看最新运行、报告、Agent 链路和证据。</p>
        </section>
      )}
      {processing.historyDetail && (
        <>
          <section className="panel">
            <div className="panel-heading-row">
              <div>
                <h2>{processing.historyDetail.ticket_id}</h2>
                <p className="muted">{processing.historyDetail.input_text}</p>
              </div>
              <span className={`status-chip status-${processing.historyDetail.latest_run?.status ?? 'pending'}`}>
                最新运行：{processing.historyDetail.latest_run ? STATUS_LABELS[processing.historyDetail.latest_run.status] : '未处理'}
              </span>
            </div>
            <dl className="details-grid">
              <dt>工单状态</dt>
              <dd>{TICKET_STATUS_LABELS[processing.historyDetail.ticket_status]}</dd>
              <dt>根因分析</dt>
              <dd>{processing.historyDetail.root_cause || '暂无'}</dd>
              <dt>修复动作</dt>
              <dd>{processing.historyDetail.fix_action || '暂无'}</dd>
              <dt>验证方式</dt>
              <dd>{processing.historyDetail.verification || '暂无'}</dd>
              <dt>关闭时间</dt>
              <dd>{processing.historyDetail.closed_at || '未关闭'}</dd>
              <dt>运行</dt>
              <dd>{processing.historyDetail.latest_run?.run_id ?? '未处理'}</dd>
              <dt>模式</dt>
              <dd><MockDataBadge mode={processing.historyDetail.data_mode} /></dd>
              <dt>更新时间</dt>
              <dd>{processing.historyDetail.updated_at}</dd>
              <dt>证据数</dt>
              <dd>{visibleEvidence.length}</dd>
            </dl>
            {processing.historyDetail.ticket_status !== 'resolved' &&
             processing.historyDetail.ticket_status !== 'closed' ? (
              <ResolveTicketPanel
                onResolve={handleResolveTicket}
                onClose={() => handleUpdateLifecycle({ ticket_status: 'closed' })}
                onReopen={() => handleUpdateLifecycle({ ticket_status: 'open' })}
                onInProgress={() => handleUpdateLifecycle({ ticket_status: 'in_progress' })}
                onReprocess={handleReprocessSelectedTicket}
              />
            ) : (
              <div className="button-row compact-buttons" aria-label="工单生命周期操作">
                <button type="button" onClick={() => handleUpdateLifecycle({ ticket_status: 'open' })}>
                  重新打开
                </button>
                <button type="button" onClick={handleReprocessSelectedTicket}>
                  重新处理此工单
                </button>
              </div>
            )}
          </section>
          <TicketRunDetailPanel detail={processing.historyDetail} />
          {isSupportResult ? (
            <SupportReplyPanel
              report={processing.result?.report}
              routing={processing.result?.routing}
              supportResult={processing.result?.support_result}
              draft={processing.historyDetail.support_reply_draft}
              saving={history.loading}
              onSaveDraft={handleUpdateSupportReplyDraft}
              onEvidenceSelect={setSelectedEvidenceId}
            />
          ) : (
            <ResultReport report={processing.result?.report} />
          )}
          {processing.result?.notification ? (
            <NotificationStatus notification={processing.result.notification as Record<string, unknown>} />
          ) : null}
          <AgentTimeline
            events={processing.events}
            trace={processing.restTrace}
            storedRuns={processing.storedAgentRuns}
            cancelExplanation={processing.cancelExplanation}
            onEvidenceSelect={setSelectedEvidenceId}
          />
          <EvidencePanel
            evidence={visibleEvidence}
            selectedEvidenceId={selectedEvidenceId}
            onSelectEvidence={setSelectedEvidenceId}
          />
          <ReviewerPanel
            review={
              processing.historyDetail?.latest_run?.response?.review ??
              processing.result?.review
            }
            onEvidenceSelect={setSelectedEvidenceId}
          />
        </>
      )}
    </aside>
  )

  const knowledgePage = (
    <div className="module-page knowledge-page">
      <section className="panel">
        <div className="panel-heading-row">
          <div>
            <h1>知识库 / SOP</h1>
            <p className="muted">展示当前服务台使用的 SOP 与知识库文章，供诊断和路由建议引用。</p>
          </div>
          <MockDataBadge mode={knowledgeDataMode} />
        </div>
        <p className="notice">
          {sourceNotice(
            knowledgeDataMode,
            '当前知识库来自后端真实知识源；飞书文档只作为知识参考，不代表当前故障事实。',
            '当前知识库来自本地 mock 知识库数据，未接入真实 ITSM、Confluence 或企业知识库系统。',
          )}
        </p>
      </section>
      <ErrorPanel error={deskResources.error} />
      {deskResources.loading && <p className="muted">正在加载知识库...</p>}
      {!deskResources.loading && deskResources.knowledgeItems.length === 0 && !deskResources.error && (
        <section className="panel"><p className="muted">该服务台暂无知识库文章。</p></section>
      )}
      <section className="knowledge-grid" aria-label="SOP 文档列表">
        {deskResources.knowledgeItems.map((doc) => (
          <article className="panel sop-card" key={doc.article_id}>
            <div className="panel-heading-row">
              <div>
                <h2>{doc.title}</h2>
                <p className="muted">{doc.summary}</p>
              </div>
              <MockDataBadge mode={doc.data_mode} />
            </div>
            <dl className="details-grid">
              <dt>文章 ID</dt>
              <dd>{doc.article_id}</dd>
              <dt>服务</dt>
              <dd>{doc.service}</dd>
              <dt>质量</dt>
              <dd>{doc.quality}</dd>
              <dt>获取时间</dt>
              <dd>{doc.retrieved_at}</dd>
              <dt>来源</dt>
              <dd>{doc.source_name}</dd>
              <dt>质量说明</dt>
              <dd>{doc.quality_reason || '未提供'}</dd>
              <dt>链接</dt>
              <dd>{doc.trace_uri ? <a href={doc.trace_uri}>{doc.trace_uri}</a> : '未提供'}</dd>
              <dt>证据</dt>
              <dd>{doc.evidence_id}</dd>
            </dl>
            <div className="list-block">
              <h3>处理步骤</h3>
              <ul>
                {doc.actions.map((action) => (
                  <li key={action}>{action}</li>
                ))}
              </ul>
            </div>
          </article>
        ))}
      </section>
    </div>
  )

  const reportPage = (
    <div className="module-page report-page">
      <section className="panel">
        <div className="panel-heading-row">
          <div>
            <h1>报表</h1>
            <p className="muted">基于已加载的历史请求生成统计卡片，不使用伪造 BI 数据。</p>
          </div>
          <MockDataBadge mode={globalDataMode} />
        </div>
        <p className="notice">总工单数来自后端历史总数；状态、优先级和服务分布基于最近最多 100 条已加载记录。</p>
      </section>
      <section className="report-stat-grid" aria-label="历史统计卡片">
        <article className="dashboard-card report-stat-card">
          <span>总工单数</span>
          <strong>{total}</strong>
        </article>
        <article className="dashboard-card report-stat-card">
          <span>已解决 / 关闭</span>
          <strong>{statusCounts.resolved}</strong>
        </article>
        <article className="dashboard-card report-stat-card">
          <span>失败 / 未解决</span>
          <strong>{statusCounts.unresolved}</strong>
        </article>
        <article className="dashboard-card report-stat-card">
          <span>已取消</span>
          <strong>{statusCounts.cancelled}</strong>
        </article>
        <article className="dashboard-card report-stat-card">
          <span>P1 数量</span>
          <strong>{statusCounts.p1}</strong>
        </article>
        <article className="dashboard-card report-stat-card">
          <span>payment-service</span>
          <strong>{statusCounts.payment}</strong>
        </article>
        <article className="dashboard-card report-stat-card">
          <span>当前详情证据数</span>
          <strong>{visibleEvidence.length}</strong>
        </article>
      </section>
      <section className="panel recent-record-list">
        <h2>最近处理记录</h2>
        {items.length === 0 && <p className="muted">暂无历史工单。</p>}
        {items.length > 0 && (
          <div className="request-table-wrap">
            <table className="request-table" aria-label="最近处理记录">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>主题</th>
                  <th>状态</th>
                  <th>优先级</th>
                  <th>服务</th>
                  <th>更新时间</th>
                </tr>
              </thead>
              <tbody>
                {items.slice(0, 10).map((item) => (
                  <tr key={item.ticket_id}>
                    <td className="request-id">{item.ticket_id}</td>
                    <td>{item.report_title || item.summary}</td>
                    <td>
                      <span className={`status-chip status-${item.status}`}>{STATUS_LABELS[item.status]}</span>
                    </td>
                    <td><span className="priority-chip">{item.priority || '未知'}</span></td>
                    <td>{item.affected_service || '未知服务'}</td>
                    <td>{item.updated_at}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  )

  function renderModule(): JSX.Element {
    if (activeModule === '首页') {
      return (
        <div className="module-page home-page service-portal-home">
          <section className="panel service-portal-panel" aria-label="服务台入口">
            <div className="service-portal-heading">
              <h1>选择您要报告问题的服务台</h1>
              <p className="muted">IntelliTicket Portal 为内部服务请求提供统一入口，当前处理默认使用真实数据模式。</p>
            </div>
            <div className="service-desk-entry-grid">
              <button
                className="service-desk-entry-card"
                type="button"
                onClick={enterOperationsDesk}
              >
                <span className="service-desk-icon" aria-hidden="true">🖥️</span>
                <strong>IT Helpdesk / IT 运维服务台</strong>
                <span>处理生产系统告警、服务故障、性能异常和变更影响。</span>
                <span className="muted">示例：支付服务超时、数据库连接池耗尽、接口 5xx、发布后异常。</span>
              </button>
              <button
                className="service-desk-entry-card"
                type="button"
                onClick={enterSupportDesk}
              >
                <span className="service-desk-icon" aria-hidden="true">🛠️</span>
                <strong>基础设施 / 内部支持服务台</strong>
                <span>处理员工账号、权限申请、VPN、办公网和内部系统访问问题。</span>
                <span className="muted">示例：申请监控权限、VPN 连不上、打不开内部系统、新员工账号问题。</span>
              </button>
            </div>
          </section>
        </div>
      )
    }

    if (activeModule === '请求') {
      return (
        <div className="request-center-layout">
          {requestList}
          {requestDetailDrawer}
        </div>
      )
    }

    if (activeModule === '服务目录') {
      return serviceCatalogPage
    }

    if (activeModule === '智能处理') {
      return (
        <div className="servicedesk-main ai-module-main">
          <BackendConnectionPanel
            defaultUrl={apiBaseUrl}
            value={activeApiBaseUrl}
            onChange={setActiveApiBaseUrl}
          />
          {ticketWork}
          {inspector}
        </div>
      )
    }

    if (activeModule === '知识库') {
      return knowledgePage
    }

    if (activeModule === '报表') {
      return reportPage
    }

    if (activeModule === '设置') {
      return (
        <div className="module-page settings-page">
          <BackendConnectionPanel
            defaultUrl={apiBaseUrl}
            value={activeApiBaseUrl}
            onChange={setActiveApiBaseUrl}
          />
          <section className="panel">
            <h2>实例设置</h2>
            <dl className="details-grid">
              <dt>部署模式</dt>
              <dd>单公司单实例</dd>
              <dt>数据模式</dt>
              <dd>real / 飞书 Drive 知识源；证据仍按来源标记</dd>
              <dt>后端地址</dt>
              <dd>{activeApiBaseUrl}</dd>
              <dt>安全边界</dt>
              <dd>当前 MVP 未实现登录和权限，内网部署需要配合网络访问控制。</dd>
            </dl>
          </section>
        </div>
      )
    }

    return (
      <div className="module-page placeholder-page">
        <section className="panel empty-module-panel">
          <h2>{activeModule}模块暂未实现</h2>
          <p className="muted">
            当前 MVP 聚焦工单请求、智能处理、Agent 执行链路和证据展示；该模块保留为后续扩展入口。
          </p>
        </section>
      </div>
    )
  }

  if (activeModule === '首页') {
    return renderModule()
  }

  if (!auth.isLoggedIn) {
    return (
      <LoginPage
        loading={auth.loading}
        error={auth.error}
        onLogin={(uid, pwd) => auth.login({ user_id: uid, password: pwd })}
      />
    )
  }

  if (auth.isEmployee) {
    return (
      <main className="servicedesk-shell">
        <header className="servicedesk-topbar">
          <div className="servicedesk-brand">
            <span className="brand-mark">📋</span>
            <strong>IntelliTicket</strong>
          </div>
          <div className="global-status" aria-label="用户信息">
            <span className="status-chip">{auth.user?.name}（员工）</span>
            <button className="return-portal-button" type="button" onClick={auth.logout}>
              退出登录
            </button>
          </div>
        </header>
        <EmployeeDashboard
          token={auth.auth?.token ?? ''}
          userName={auth.user?.name ?? ''}
          onTicketSelect={handleEmployeeSelectTicket}
          refreshKey={0}
        />
        {selectedTicketId ? (
          <section className="workspace-panels" aria-label="工单详情">
            <TicketRunDetailPanel detail={processing.historyDetail} />
          </section>
        ) : null}
      </main>
    )
  }

  return (
    <main className="servicedesk-shell">
      <header className="servicedesk-topbar">
        <div className="servicedesk-brand">
          <span className="brand-mark">{activePortalConfig.mark}</span>
          <strong>{activePortalConfig.title}</strong>
        </div>
        <nav className="module-tabs" aria-label="模块导航">
          {activePortalConfig.tabs.map((tab) => (
            <button
              key={tab}
              className={tab === activeModule ? 'module-tab module-tab-active' : 'module-tab'}
              type="button"
              aria-current={tab === activeModule ? 'page' : undefined}
              onClick={() => setActiveModule(tab)}
            >
              {tab}
            </button>
          ))}
        </nav>
        <div className="global-status" aria-label="全局状态">
          <span className="status-chip">{auth.user?.name}（运维）</span>
          <button className="return-portal-button" type="button" onClick={auth.logout}>
            退出登录
          </button>
          <button className="return-portal-button" type="button" onClick={() => setActiveModule('首页')}>
            返回门户
          </button>
          <MockDataBadge mode={globalDataMode} />
          <span className="status-chip">单公司单实例</span>
          <span className="status-chip">{modeLabel}</span>
        </div>
      </header>

      <section className="service-subbar" aria-label="实例状态">
        <span>后端：{activeApiBaseUrl}</span>
        <span>当前页：{activeModule}</span>
        <span>{activePortalConfig.examples}</span>
        <span>数据来源：{globalDataMode === 'real' ? '真实后端 / 飞书 Drive 知识源' : '本地 mock_data'}</span>
      </section>

      <section className="dashboard-cards" aria-label="请求概览">
        <article className="dashboard-card">
          <span>历史工单</span>
          <strong>{total}</strong>
        </article>
        <article className="dashboard-card">
          <span>未解决</span>
          <strong>{statusCounts.unresolved}</strong>
        </article>
        <article className="dashboard-card">
          <span>已解决 / 关闭</span>
          <strong>{statusCounts.resolved}</strong>
        </article>
        <article className="dashboard-card">
          <span>P1 数量</span>
          <strong>{statusCounts.p1}</strong>
        </article>
        <article className="dashboard-card">
          <span>影响服务</span>
          <strong>{currentClassification?.affected_service ?? '待识别'}</strong>
        </article>
      </section>

      {renderModule()}
    </main>
  )
}
