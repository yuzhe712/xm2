interface TicketInputPanelProps {
  value: string
  disabled: boolean
  onChange: (value: string) => void
}

export function TicketInputPanel({ value, disabled, onChange }: TicketInputPanelProps): JSX.Element {
  return (
    <section className="panel ticket-input-panel">
      <h2>当前工单</h2>
      <p className="muted">输入自然语言告警或从左侧模板带入，处理结果会保留证据链。</p>
      <textarea
        aria-label="工单内容"
        disabled={disabled}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder="输入自然语言运维告警工单..."
      />
    </section>
  )
}
