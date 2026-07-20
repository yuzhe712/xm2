interface MockDataBadgeProps {
  mode?: string
}

export function MockDataBadge({ mode = 'mock' }: MockDataBadgeProps): JSX.Element {
  const label = mode === 'real' ? '真实数据 real' : mode === 'mock' ? '模拟数据 mock' : `数据模式 ${mode}`
  return <span className="badge badge-warning">{label}</span>
}
