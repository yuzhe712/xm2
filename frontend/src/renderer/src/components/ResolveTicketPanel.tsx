import { useState } from 'react'

interface ResolveTicketPanelProps {
  onResolve: (rootCause: string, fixAction: string, verification: string) => void
  onClose: () => void
  onReopen: () => void
  onInProgress: () => void
  onReprocess: () => void
}

export default function ResolveTicketPanel({
  onResolve,
  onClose,
  onReopen,
  onInProgress,
  onReprocess,
}: ResolveTicketPanelProps) {
  const [showResolve, setShowResolve] = useState(false)
  const [rootCause, setRootCause] = useState('')
  const [fixAction, setFixAction] = useState('')
  const [verification, setVerification] = useState('')
  const [showAll, setShowAll] = useState(false)

  const canResolve =
    rootCause.trim().length > 0 &&
    fixAction.trim().length > 0 &&
    verification.trim().length > 0

  const handleResolve = () => {
    if (!canResolve) return
    onResolve(rootCause.trim(), fixAction.trim(), verification.trim())
    setRootCause('')
    setFixAction('')
    setVerification('')
    setShowResolve(false)
  }

  return (
    <div className="resolve-panel">
      {showResolve ? (
        <div className="resolve-form">
          <label className="resolve-label">
            根因分析（导致此问题的根本原因是什么？）
          </label>
          <textarea
            className="resolve-textarea"
            value={rootCause}
            onChange={(e) => setRootCause(e.target.value)}
            placeholder="例如：payment-db 主库连接池配置为默认值 50，高峰期并发请求超过该上限导致连接等待超时。"
            rows={3}
            autoFocus
          />
          <label className="resolve-label">
            修复动作（你做了什么来修复此问题？）
          </label>
          <textarea
            className="resolve-textarea"
            value={fixAction}
            onChange={(e) => setFixAction(e.target.value)}
            placeholder="例如：已将 payment-db 主库连接池上限调整为 200，并重启数据库服务使配置生效。"
            rows={3}
          />
          <label className="resolve-label">
            验证方式（如何确认问题已修复？）
          </label>
          <textarea
            className="resolve-textarea"
            value={verification}
            onChange={(e) => setVerification(e.target.value)}
            placeholder="例如：监控确认支付服务超时率已从 35% 降至 0.1% 以下，订单量恢复至 1000/min，持续观测 30 分钟无异常。"
            rows={3}
          />
          <div className="resolve-actions">
            <button className="button-primary" onClick={handleResolve} disabled={!canResolve}>
              确认已解决
            </button>
            <button className="button-secondary" onClick={() => setShowResolve(false)}>
              取消
            </button>
          </div>
        </div>
      ) : (
        <div className="button-row compact-buttons" aria-label="工单生命周期操作">
          <button type="button" onClick={onInProgress}>
            标记处理中
          </button>
          <button
            type="button"
            className="button-resolve"
            onClick={() => setShowResolve(true)}
          >
            标记已解决
          </button>
          {showAll && (
            <>
              <button type="button" onClick={onClose}>
                关闭工单
              </button>
              <button type="button" onClick={onReopen}>
                重新打开
              </button>
            </>
          )}
          <button
            type="button"
            className="button-more"
            onClick={() => setShowAll(!showAll)}
          >
            {showAll ? '收起' : '更多操作'}
          </button>
          <button type="button" onClick={onReprocess}>
            重新处理此工单
          </button>
        </div>
      )}
    </div>
  )
}
