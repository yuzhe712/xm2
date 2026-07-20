import { useCallback, useEffect, useState } from 'react'

import { getTicketDetail, listTickets, reprocessTicket, TicketApiError, updateSupportReplyDraft, updateTicketLifecycle } from '../api/tickets'
import type { ApiErrorPayload, DeskId, SupportReplyDraftUpdateRequest, TicketHistoryDetailResponse, TicketHistorySummary, TicketLifecycleUpdateRequest } from '../types/tickets'

interface UseTicketHistoryOptions {
  apiBaseUrl?: string
  deskId?: DeskId
  token?: string
}

interface UseTicketHistoryResult {
  items: TicketHistorySummary[]
  total: number
  loading: boolean
  error: TicketApiError | ApiErrorPayload['error'] | Error | null
  refresh: () => Promise<void>
  selectTicket: (ticketId: string) => Promise<TicketHistoryDetailResponse | null>
  updateLifecycle: (ticketId: string, request: TicketLifecycleUpdateRequest) => Promise<TicketHistoryDetailResponse | null>
  updateSupportDraft: (ticketId: string, request: SupportReplyDraftUpdateRequest) => Promise<TicketHistoryDetailResponse | null>
  reprocess: (ticketId: string) => Promise<TicketHistoryDetailResponse | null>
}

export function useTicketHistory(options: UseTicketHistoryOptions = {}): UseTicketHistoryResult {
  const { apiBaseUrl, deskId, token = '' } = options
  const [items, setItems] = useState<TicketHistorySummary[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<TicketApiError | ApiErrorPayload['error'] | Error | null>(null)

  const refresh = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const response = await listTickets(100, 0, fetch, apiBaseUrl, deskId)
      setItems(response.items)
      setTotal(response.total)
    } catch (err) {
      setError(err instanceof Error ? err : new Error('历史工单查询失败'))
    } finally {
      setLoading(false)
    }
  }, [apiBaseUrl, deskId])

  const selectTicket = useCallback(async (ticketId: string) => {
    setLoading(true)
    setError(null)
    try {
      return await getTicketDetail(ticketId, fetch, apiBaseUrl)
    } catch (err) {
      setError(err instanceof Error ? err : new Error('历史工单详情查询失败'))
      return null
    } finally {
      setLoading(false)
    }
  }, [apiBaseUrl])

  const updateLifecycle = useCallback(async (ticketId: string, request: TicketLifecycleUpdateRequest) => {
    setLoading(true)
    setError(null)
    try {
      const detail = await updateTicketLifecycle(ticketId, request, token, fetch, apiBaseUrl)
      await refresh()
      return detail
    } catch (err) {
      setError(err instanceof Error ? err : new Error('工单生命周期更新失败'))
      return null
    } finally {
      setLoading(false)
    }
  }, [apiBaseUrl, token, refresh])

  const updateSupportDraft = useCallback(async (ticketId: string, request: SupportReplyDraftUpdateRequest) => {
    setLoading(true)
    setError(null)
    try {
      const detail = await updateSupportReplyDraft(ticketId, request, token, fetch, apiBaseUrl)
      await refresh()
      return detail
    } catch (err) {
      setError(err instanceof Error ? err : new Error('内部支持回复草稿保存失败'))
      return null
    } finally {
      setLoading(false)
    }
  }, [apiBaseUrl, token, refresh])

  const reprocess = useCallback(async (ticketId: string) => {
    setLoading(true)
    setError(null)
    try {
      const detail = await reprocessTicket(ticketId, token, fetch, apiBaseUrl)
      await refresh()
      return detail
    } catch (err) {
      setError(err instanceof Error ? err : new Error('工单重新处理失败'))
      return null
    } finally {
      setLoading(false)
    }
  }, [apiBaseUrl, token, refresh])

  useEffect(() => {
    void refresh()
  }, [refresh])

  return { items, total, loading, error, refresh, selectTicket, updateLifecycle, updateSupportDraft, reprocess }
}
