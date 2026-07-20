interface ProcessingControlsProps {
  canSubmit: boolean
  canCancel: boolean
  modeLabel: string
  onRest: () => void
  onWebSocket: () => void
  onCancel: () => void
}

export function ProcessingControls({
  canSubmit,
  canCancel,
  modeLabel,
  onRest,
  onWebSocket,
  onCancel,
}: ProcessingControlsProps): JSX.Element {
  return (
    <section className="panel controls-panel">
      <div className="button-row">
        <button type="button" disabled={!canSubmit} onClick={onRest}>
          同步处理 / REST
        </button>
        <button type="button" disabled={!canSubmit} onClick={onWebSocket}>
          实时处理 / WebSocket
        </button>
        {canCancel && (
          <button className="danger" type="button" onClick={onCancel}>
            取消处理
          </button>
        )}
      </div>
      <p className="muted">处理状态：{modeLabel}</p>
    </section>
  )
}
