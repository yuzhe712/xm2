export type DataMode = 'mock' | 'demo' | 'real'
export type DeskId = 'ops' | 'support'
export type RunStatus = 'completed' | 'failed' | 'cancelled' | 'pending'
export type TicketStatus = 'pending' | 'open' | 'in_progress' | 'resolved' | 'closed' | 'cancelled'
export type SupportReplyDraftStatus = 'draft' | 'approved' | 'sent' | 'discarded'

export interface LoginRequest {
  user_id: string
  password: string
}

export interface LoginResponse {
  token: string
  user_id: string
  name: string
  role: string
}

export interface TicketSubmitRequest {
  text: string
  desk_id: DeskId
}

export interface TicketSubmitResponse {
  ticket_id: string
  status: string
  created_at: string
  text: string
  desk_id: DeskId
  submitter: string
  assessed_priority?: string | null
  assessed_priority_reason?: string | null
}

export interface TicketHistorySummary {
  ticket_id: string
  desk_id: DeskId
  latest_run_id: string | null
  created_at: string
  updated_at: string
  data_mode: DataMode
  status: RunStatus
  ticket_status: TicketStatus
  submitter?: string | null
  assessed_priority?: string | null
  assessed_priority_reason?: string | null
  sla_deadline?: string | null
  claimed_by?: string | null
  claimed_at?: string | null
  assigned_team?: string | null
  resolution_summary?: string | null
  closed_at?: string | null
  summary?: string | null
  affected_service?: string | null
  priority?: string | null
  report_title?: string | null
}

export interface CatalogItem {
  evidence_id: string
  source_type: string
  source_id: string
  source_name: string
  retrieved_at?: string | null
  observed_at?: string | null
  desk_scope: DeskId
  id: string
  title: string
  category: string
  priority_hint: string
  affected_service: string
  description: string
  template_text: string
  quality: string
  data_mode: DataMode
  summary: string
}

export interface CatalogResponse {
  desk_id: DeskId
  data_mode: DataMode
  items: CatalogItem[]
}

export interface KnowledgeArticle {
  evidence_id: string
  source_type: string
  source_id: string
  source_name: string
  retrieved_at?: string | null
  observed_at?: string | null
  desk_scope: DeskId
  service: string
  article_id: string
  title: string
  actions: string[]
  quality: string
  data_mode: DataMode
  summary: string
  trace_uri?: string | null
  quality_reason?: string | null
}

export interface KnowledgeResponse {
  desk_id: DeskId
  data_mode: DataMode
  items: KnowledgeArticle[]
}

export interface TicketProcessRequest {
  text: string
  desk_id: DeskId
}

export interface EvidenceRef {
  evidence_id: string
}

export interface Evidence {
  evidence_id: string
  source_type: string
  source_id: string
  source_name: string
  observed_at?: string | null
  retrieved_at?: string | null
  service?: string | null
  metric_name?: string | null
  value?: unknown
  unit?: string | null
  quality: string
  data_mode: DataMode
  confidence?: number | null
  summary: string
  trace_uri?: string | null
  freshness?: string | null
  quality_reason?: string | null
  producer?: string | null
  run_id?: string | null
}

export interface TicketClassification {
  category: string
  summary: string
  affected_service: string | null
  symptoms: string[]
  priority: string
  priority_reason: string
  extracted_metrics: Record<string, unknown>
  evidence_ids: string[]
}

export interface ServiceContext {
  service_id: string
  name: string
  display_name: string
  aliases: string[]
  owner_team: string
  criticality: string
  dependencies: string[]
  data_mode: DataMode
}

export interface MetricSnapshot {
  evidence_id: string
  metric_name: string
  value: unknown
  unit: string
  observed_at: string
  quality: string
  summary: string
  data_mode: DataMode
}

export interface DeploymentRecord {
  evidence_id: string
  version: string
  deployed_at: string
  author: string
  summary: string
  data_mode: DataMode
}

export interface HistoricalIncident {
  evidence_id: string
  incident_id: string
  root_cause: string
  summary: string
  data_mode: DataMode
}

export interface SopDocument {
  evidence_id: string
  sop_id: string
  title: string
  actions: string[]
  data_mode: DataMode
}

export interface RetrievedContext {
  service: ServiceContext | null
  metrics: MetricSnapshot[]
  deployments: DeploymentRecord[]
  historical_incidents: HistoricalIncident[]
  sop_documents: SopDocument[]
  unknowns: string[]
}

export interface CandidateRootCause {
  cause: string
  evidence_ids: string[]
  confidence: number
  reasoning_summary: string
}

export interface DiagnosisResult {
  candidate_root_causes: CandidateRootCause[]
  unknowns: string[]
  abstentions: string[]
}

export interface RecommendedAction {
  action: string
  evidence_ids: string[]
}

export interface RoutingRecommendation {
  recommended_team: string | null
  recommended_actions: RecommendedAction[]
  escalation: string
  sop_refs: string[]
}

export interface FinalReport {
  title: string
  summary: string
  facts: string[]
  derived_findings: string[]
  assumptions: string[]
  unknowns: string[]
  recommendations: string[]
}

export interface WorkflowStepTrace {
  step: string
  status: string
  started_at: string
  completed_at: string
  summary: string
  evidence_ids: string[]
}

export interface OpsTicketResult {
  affected_service: string | null
  candidate_root_causes: CandidateRootCause[]
  recommended_actions: RecommendedAction[]
  assigned_team: string | null
  sop_refs: string[]
  evidence_ids: string[]
}

export interface SupportTicketResult {
  request_type: string
  matched_articles: string[]
  reply_suggestions: string[]
  recommended_team: string | null
  escalation: string
  evidence_ids: string[]
}

export interface TicketProcessResponse {
  ticket_id: string
  run_id: string
  data_mode: DataMode
  classification: TicketClassification
  context: RetrievedContext
  diagnosis: DiagnosisResult
  routing: RoutingRecommendation
  report: FinalReport
  agent_trace: WorkflowStepTrace[]
  evidence: Evidence[]
  review?: ReviewResult | null
  ops_result?: OpsTicketResult | null
  support_result?: SupportTicketResult | null
  notification?: Record<string, unknown> | null
}

export interface ReviewIssue {
  severity: 'critical' | 'warning' | 'info'
  category: string
  description: string
  affected_fields: string[]
  evidence_ids: string[]
}

export interface ReviewResult {
  review_status: 'consistent' | 'flagged' | 'abstain'
  issues: ReviewIssue[]
  recommendation: string
  confidence: number
  evidence_ids: string[]
}

export interface ReActStep {
  step_index: number
  decision_summary: string
  action: string
  action_input_summary: string
  observation_summary: string
  evidence_ids: string[]
}

export interface AgentTaskError {
  code: string
  message: string
  details: Record<string, unknown>
}

export interface StoredAgentRun {
  sequence: number
  task_id: string
  agent_name: string
  step: string
  status: string
  route_decision: unknown | null
  observations: string[]
  react_steps?: ReActStep[]
  evidence_ids: string[]
  error: AgentTaskError | null
  started_at: string
  completed_at?: string | null
}

export interface TicketLifecycleUpdateRequest {
  ticket_status?: TicketStatus
  resolution_summary?: string | null
  root_cause?: string | null
  fix_action?: string | null
  verification?: string | null
}

export interface SupportReplyDraftUpdateRequest {
  reply_text: string
  report_summary?: string | null
  evidence_ids: string[]
  status?: SupportReplyDraftStatus
  editor?: string | null
}

export interface SupportReplyDraftResponse {
  draft_id: string
  ticket_id: string
  run_id: string
  source: string
  reply_text: string
  report_summary?: string | null
  evidence_ids: string[]
  status: SupportReplyDraftStatus
  editor?: string | null
  created_at: string
  updated_at: string
  approved_at?: string | null
  sent_at?: string | null
}

export interface TicketHistoryListResponse {
  items: TicketHistorySummary[]
  limit: number
  offset: number
  total: number
}

export interface StoredRunDetail {
  run_id: string
  status: RunStatus
  data_mode: DataMode
  route_mode: string
  started_at: string
  completed_at: string
  response: TicketProcessResponse | null
  error: AgentTaskError | null
  agent_runs: StoredAgentRun[]
  supervisor_decisions: unknown[]
  evidence: Evidence[]
}

export interface TicketHistoryDetailResponse {
  ticket_id: string
  desk_id: DeskId
  input_text: string
  data_mode: DataMode
  ticket_status: TicketStatus
  submitter?: string | null
  assigned_team?: string | null
  resolution_summary?: string | null
  root_cause?: string | null
  fix_action?: string | null
  verification?: string | null
  closed_at?: string | null
  created_at: string
  updated_at: string
  support_reply_draft?: SupportReplyDraftResponse | null
  latest_run: StoredRunDetail | null
}

export interface ApiErrorPayload {
  error: {
    code: string
    message: string
    details: Record<string, unknown>
  }
}

export interface TicketProcessWsStartedEvent {
  type: 'started'
  ticket_id: string
  run_id: string
  sequence: number
  timestamp: string
}

export interface TicketProcessWsAgentProgressEvent {
  type: 'agent_progress'
  ticket_id: string
  run_id: string
  sequence: number
  timestamp: string
  agent_name: string
  step: string
  status: string
  summary: string
  evidence_refs: EvidenceRef[]
}

export interface TicketProcessWsCompletedEvent {
  type: 'completed'
  ticket_id: string
  run_id: string
  sequence: number
  timestamp: string
  result: TicketProcessResponse
}

export interface TicketProcessWsCancelledEvent {
  type: 'cancelled'
  ticket_id: string
  run_id: string
  sequence: number
  timestamp: string
  reason: string
}

export interface TicketProcessWsErrorEvent {
  type: 'error'
  ticket_id: string
  run_id: string
  sequence: number
  timestamp: string
  error: ApiErrorPayload['error']
}

export type TicketProcessWsEvent =
  | TicketProcessWsStartedEvent
  | TicketProcessWsAgentProgressEvent
  | TicketProcessWsCompletedEvent
  | TicketProcessWsCancelledEvent
  | TicketProcessWsErrorEvent
