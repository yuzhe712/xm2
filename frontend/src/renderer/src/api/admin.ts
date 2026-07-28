import type { SessionUser, ServiceCatalogItem, SlaPolicy, Team, UserRole } from '../types/workflow'
import { apiRequest } from './client'

export function listUsers(token: string): Promise<SessionUser[]> {
  return apiRequest('/api/v1/users', {}, token)
}

export function createUser(
  values: { username: string; display_name: string; role: UserRole; password: string; team_id?: string | null },
  token: string,
): Promise<SessionUser> {
  return apiRequest('/api/v1/users', { method: 'POST', body: JSON.stringify(values) }, token)
}

export function updateUser(userId: string, values: Partial<SessionUser>, token: string): Promise<SessionUser> {
  return apiRequest(`/api/v1/users/${encodeURIComponent(userId)}`, {
    method: 'PATCH', body: JSON.stringify(values),
  }, token)
}

export function listTeams(token: string): Promise<Team[]> {
  return apiRequest('/api/v1/teams', {}, token)
}

export function createTeam(values: { code: string; name: string }, token: string): Promise<Team> {
  return apiRequest('/api/v1/teams', { method: 'POST', body: JSON.stringify(values) }, token)
}

export function updateTeam(teamId: string, values: Partial<Team>, token: string): Promise<Team> {
  return apiRequest(`/api/v1/teams/${encodeURIComponent(teamId)}`, {
    method: 'PATCH', body: JSON.stringify(values),
  }, token)
}

export function listSlaPolicies(token: string): Promise<SlaPolicy[]> {
  return apiRequest('/api/v1/sla-policies', {}, token)
}

export function createSlaPolicy(
  values: Omit<SlaPolicy, 'id' | 'created_at' | 'updated_at'>,
  token: string,
): Promise<SlaPolicy> {
  return apiRequest('/api/v1/sla-policies', { method: 'POST', body: JSON.stringify(values) }, token)
}

export function updateSlaPolicy(policyId: string, values: Partial<SlaPolicy>, token: string): Promise<SlaPolicy> {
  return apiRequest(`/api/v1/sla-policies/${encodeURIComponent(policyId)}`, {
    method: 'PATCH', body: JSON.stringify(values),
  }, token)
}

export function listManagedCatalog(token: string): Promise<ServiceCatalogItem[]> {
  return apiRequest('/api/v1/service-catalog', {}, token)
}

export function createCatalogItem(
  values: Omit<ServiceCatalogItem, 'id' | 'created_at' | 'updated_at'>,
  token: string,
): Promise<ServiceCatalogItem> {
  return apiRequest('/api/v1/service-catalog', { method: 'POST', body: JSON.stringify(values) }, token)
}

export function updateCatalogItem(
  itemId: string,
  values: Partial<ServiceCatalogItem>,
  token: string,
): Promise<ServiceCatalogItem> {
  return apiRequest(`/api/v1/service-catalog/${encodeURIComponent(itemId)}`, {
    method: 'PATCH', body: JSON.stringify(values),
  }, token)
}
