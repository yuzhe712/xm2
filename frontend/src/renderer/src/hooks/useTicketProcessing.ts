import { useCallback, useRef, useState } from 'react'

import { createTicketProcessingSocket, previewReprocessTicket, processTicketRest, TicketApiError } from '../api/tickets'
import type {
  ApiErrorPayload,
  DataMode,
  DeskId,
  StoredAgentRun,
  TicketHistoryDetailResponse,
  TicketProcessResponse,
  TicketProcessWsEvent,
  WorkflowStepTrace,
} from '../types/tickets'

export type ProcessingMode =
  | 'idle'
  | 'rest-loading'
  | 'ws-connecting'
  | 'ws-running'
  | 'cancelling'
  | 'completed'
  | 'error'
  | 'cancelled'

interface UseTicketProcessingOptions {
  apiBaseUrl?: string
  token?: string
}

interface UseTicketProcessingResult {
  mode: ProcessingMode
  result: TicketProcessResponse | null
  historyDetail: TicketHistoryDetailResponse | null
  storedAgentRuns: StoredAgentRun[]
  events: TicketProcessWsEvent[]
  restTrace: WorkflowStepTrace[]
  error: TicketApiError | ApiErrorPayload['error'] | Error | null
  cancelExplanation: string | null
  isBusy: boolean
  canCancel: boolean
  runRest: (text: string, deskId: DeskId) => Promise<void>
  runReprocessPreview: (ticketId: string) => Promise<void>
  runWebSocket: (text: string, deskId: DeskId) => void
  cancelWebSocket: () => void
  showPersistedDetail: (detail: TicketHistoryDetailResponse) => void
}

const DEFAULT_DATA_MODE: DataMode = 'real'

function isTerminalMode(mode: ProcessingMode): boolean {
  return mode === 'completed' || mode === 'error' || mode === 'cancelled'
}

export function useTicketProcessing(options: UseTicketProcessingOptions = {}): UseTicketProcessingResult {
  const { apiBaseUrl, token = '' } = options
  const [mode, setMode] = useState<ProcessingMode>('idle')
  const [result, setResult] = useState<TicketProcessResponse | null>(null)
  const [historyDetail, setHistoryDetail] = useState<TicketHistoryDetailResponse | null>(null)
  const [storedAgentRuns, setStoredAgentRuns] = useState<StoredAgentRun[]>([])
  const [events, setEvents] = useState<TicketProcessWsEvent[]>([])
  const [restTrace, setRestTrace] = useState<WorkflowStepTrace[]>([])
  const [error, setError] = useState<TicketApiError | ApiErrorPayload['error'] | Error | null>(null)
  const [cancelExplanation, setCancelExplanation] = useState<string | null>(null)
  const socketRef = useRef<WebSocket | null>(null)
  const cancelRequestedRef = useRef(false)

  const resetRunState = useCallback(() => {
    setResult(null)
    setHistoryDetail(null)
    setStoredAgentRuns([])
    setEvents([])
    setRestTrace([])
    setError(null)
    setCancelExplanation(null)
    cancelRequestedRef.current = false
  }, [])

  const runRest = useCallback(
    async (text: string, deskId: DeskId) => {
      resetRunState()
      setMode('rest-loading')
      try {
        const response = await processTicketRest({ text, data_mode: DEFAULT_DATA_MODE, desk_id: deskId }, token, fetch, apiBaseUrl)
        setHistoryDetail(null)
        setStoredAgentRuns([])
        setResult(response)
        setRestTrace(response.agent_trace)
        setMode('completed')
      } catch (err) {
        setError(err instanceof Error ? err : new Error('未知 REST 错误'))
        setMode('error')
      }
    },
    [apiBaseUrl, token, resetRunState],
  )

  const runReprocessPreview = useCallback(
    async (ticketId: string) => {
      resetRunState()
      setMode('rest-loading')
      try {
        const response = await previewReprocessTicket(ticketId, token, fetch, apiBaseUrl)
        setHistoryDetail(null)
        setStoredAgentRuns([])
        setResult(response)
        setRestTrace(response.agent_trace)
        setMode('completed')
      } catch (err) {
        setError(err instanceof Error ? err : new Error('工单重新处理预览失败'))
        setMode('error')
      }
    },
    [apiBaseUrl, token, resetRunState],
  )

  const runWebSocket = useCallback(
    (text: string, deskId: DeskId) => {
      resetRunState()
      setMode('ws-connecting')
      const socket = createTicketProcessingSocket(apiBaseUrl)
      socketRef.current = socket

      socket.addEventListener('open', () => {
        setMode('ws-running')
        socket.send(
          JSON.stringify({
            type: 'start',
            request: { text, data_mode: DEFAULT_DATA_MODE, desk_id: deskId },
          }),
        )
      })

      socket.addEventListener('message', (event) => {
        const parsed = JSON.parse(event.data as string) as TicketProcessWsEvent
        setEvents((current) => [...current, parsed])

        if (parsed.type === 'completed') {
          setHistoryDetail(null)
          setStoredAgentRuns([])
          setResult(parsed.result)
          setRestTrace(parsed.result.agent_trace)
          if (cancelRequestedRef.current) {
            setCancelExplanation('处理已完成；取消请求可能晚于后端完成，符合 best-effort 语义。')
          }
          setMode('completed')
        } else if (parsed.type === 'error') {
          setError(parsed.error)
          setMode('error')
        } else if (parsed.type === 'cancelled') {
          setCancelExplanation('后端已确认取消。')
          setMode('cancelled')
        }
      })

      socket.addEventListener('error', () => {
        setError(new Error('WebSocket 连接失败，请检查后端地址、端口、CORS 和服务状态。'))
        setMode('error')
      })

      socket.addEventListener('close', () => {
        socketRef.current = null
        setMode((current) => (isTerminalMode(current) ? current : 'error'))
      })
    },
    [apiBaseUrl, resetRunState],
  )

  const showPersistedDetail = useCallback(
    (detail: TicketHistoryDetailResponse) => {
      resetRunState()
      setHistoryDetail(detail)
      if (detail.latest_run) {
        setStoredAgentRuns(detail.latest_run.agent_runs)
        if (detail.latest_run.response) {
          setResult(detail.latest_run.response)
          setRestTrace(detail.latest_run.response.agent_trace)
          setMode('completed')
          return
        }
        setResult(null)
        setRestTrace([])
        if (detail.latest_run.error) {
          setError(detail.latest_run.error)
        }
        if (detail.latest_run.status === 'cancelled') {
          setCancelExplanation('该历史运行已取消，未生成完整处理结果。')
          setMode('cancelled')
        } else {
          setMode('error')
        }
        return
      }
      // Pending ticket — no run yet
      setStoredAgentRuns([])
      setResult(null)
      setRestTrace([])
      setMode('idle')
    },
    [resetRunState],
  )

  const cancelWebSocket = useCallback(() => {
    const socket = socketRef.current
    if (!socket || socket.readyState !== WebSocket.OPEN) return
    cancelRequestedRef.current = true
    setCancelExplanation('取消请求已发送，等待后端确认。')
    setMode('cancelling')
    socket.send(JSON.stringify({ type: 'cancel', reason: 'user_cancelled' }))
  }, [])

  return {
    mode,
    result,
    historyDetail,
    storedAgentRuns,
    events,
    restTrace,
    error,
    cancelExplanation,
    isBusy: mode === 'rest-loading' || mode === 'ws-connecting' || mode === 'ws-running' || mode === 'cancelling',
    canCancel: mode === 'ws-running' || mode === 'cancelling',
    runRest,
    runReprocessPreview,
    runWebSocket,
    cancelWebSocket,
    showPersistedDetail,
  }
}
