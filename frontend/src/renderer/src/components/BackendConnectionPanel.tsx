import { useEffect, useState } from 'react'

interface BackendConnectionPanelProps {
  defaultUrl: string
  value: string
  onChange: (value: string) => void
}

function normalizeInput(value: string): string {
  return value.trim().replace(/\/$/, '')
}

export function BackendConnectionPanel({
  defaultUrl,
  value,
  onChange,
}: BackendConnectionPanelProps): JSX.Element {
  const [draft, setDraft] = useState(value)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setDraft(value)
  }, [value])

  function applyEndpoint(): void {
    const next = normalizeInput(draft)
    try {
      const url = new URL(next)
      if (url.protocol !== 'http:' && url.protocol !== 'https:') {
        setError('后端地址必须以 http:// 或 https:// 开头。')
        return
      }
      setError(null)
      onChange(next)
    } catch {
      setError('后端地址无效，请输入完整的 http(s) 地址。')
    }
  }

  function resetEndpoint(): void {
    setError(null)
    setDraft(defaultUrl)
    onChange(defaultUrl)
  }

  return (
    <section className="panel connection-panel" aria-label="后端连接设置">
      <div>
        <h2>后端连接</h2>
        <p className="muted">默认连接本机，也可指向同一公司内网部署的后端实例。</p>
      </div>
      <label className="endpoint-row">
        <span>地址</span>
        <input
          aria-label="后端地址"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter') applyEndpoint()
          }}
        />
      </label>
      {error && <p className="notice">{error}</p>}
      <div className="button-row compact-buttons">
        <button type="button" onClick={applyEndpoint}>
          应用地址
        </button>
        <button className="secondary" type="button" onClick={resetEndpoint}>
          恢复默认
        </button>
      </div>
    </section>
  )
}
