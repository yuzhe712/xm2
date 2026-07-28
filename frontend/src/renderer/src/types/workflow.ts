import type { DeskId, TicketHistoryDetailResponse, TicketHistorySummary, TicketStatus } from './tickets'

export type UserRole = 'employee' | 'operator' | 'admin'
export type CommentVisibility = 'public' | 'internal'

export interface SessionUser {
  id: string
  username: string
  display_name: string
  role: UserRole
  team_id: string | null
  is_active: boolean
}

export interface WorkflowTicket {
  ticket_id: string
  title: string
  description: string
  desk_id: DeskId
  data_mode: 'mock' | 'real'
  status: TicketStatus
  priority: string | null
  category: string | null
  submitter_id: string
  submitter: string
  assigned_team_id: string | null
  assigned_team: string | null
  assignee_id: string | null
  claimed_by: string | null
  resolution_summary: string | null
  root_cause: string | null
  fix_action: string | null
  verification: string | null
  response_due_at: string | null
  resolution_due_at: string | null
  first_responded_at: string | null
  resolved_at: string | null
  closed_at: string | null
  version: number
  created_at: string
  updated_at: string
}

export interface TicketComment {
  id: string
  ticket_id: string
  author_id: string
  author: string
  visibility: CommentVisibility
  body: string
  created_at: string
  updated_at: string
}

export interface TicketEvent {
  id: string
  ticket_id: string
  actor_id: string | null
  actor: string | null
  event_type: string
  from_status: TicketStatus | null
  to_status: TicketStatus | null
  visibility: CommentVisibility
  payload: Record<string, unknown>
  created_at: string
}

export interface TicketAttachment {
  id: string
  ticket_id: string
  uploader_id: string
  original_name: string
  content_type: string
  size_bytes: number
  sha256: string
  created_at: string
}

export interface AiRun {
  id: string
  ticket_id: string
  status: 'queued' | 'running' | 'completed' | 'failed' | 'cancelled'
  stage: string
  progress: number
  pipeline_version: string
  provider: string
  model: string
  prompt_version: string
  result: Record<string, unknown> | null
  evidence: Array<Record<string, unknown>>
  confidence: number | null
  error_code: string | null
  error_message: string | null
  duration_ms: number | null
  decision: 'accepted' | 'modified' | 'rejected' | null
  retry_count: number
  created_at: string
  updated_at: string
}

export interface Team {
  id: string
  code: string
  name: string
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface SlaPolicy {
  id: string
  name: string
  priority: 'P1' | 'P2' | 'P3' | 'P4'
  response_minutes: number
  resolution_minutes: number
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface ServiceCatalogItem {
  id: string
  service_key: string
  name: string
  description: string
  desk_id: DeskId
  team_id: string | null
  keywords: string[]
  default_category: string | null
  is_active: boolean
  created_at: string
  updated_at: string
}

export type TicketListItem = TicketHistorySummary
export type TicketDetailRecord = TicketHistoryDetailResponse
