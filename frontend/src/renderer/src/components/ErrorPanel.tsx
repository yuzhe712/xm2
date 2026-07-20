import type { TicketApiError } from '../api/tickets'
import type { ApiErrorPayload } from '../types/tickets'

interface ErrorPanelProps {
  error: TicketApiError | ApiErrorPayload['error'] | Error | null
}

export function ErrorPanel({ error }: ErrorPanelProps): JSX.Element | null {
  if (!error) return null

  const code = 'code' in error ? error.code : 'CLIENT_ERROR'
  const message = error.message
  const details = 'details' in error ? error.details : {}

  return (
    <section className="panel error-panel" role="alert">
      <h2>错误</h2>
      <p><strong>{code}</strong>：{message}</p>
      {Object.keys(details).length > 0 && <pre>{JSON.stringify(details, null, 2)}</pre>}
    </section>
  )
}
