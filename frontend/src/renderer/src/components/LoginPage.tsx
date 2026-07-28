import { useState } from 'react'

interface LoginPageProps {
  loading: boolean
  error: string | null
  onLogin: (userId: string, password: string) => void
}

export default function LoginPage({ loading, error, onLogin }: LoginPageProps) {
  const [userId, setUserId] = useState('')
  const [password, setPassword] = useState('')

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (userId.trim() && password.trim()) {
      onLogin(userId.trim(), password)
    }
  }

  return (
    <div className="login-page">
      <form className="login-card" onSubmit={handleSubmit}>
        <div className="login-header">
          <h1>IntelliTicket</h1>
          <p className="muted">企业级智能工单平台</p>
        </div>

        {error && (
          <div className="login-error" role="alert">
            {error}
          </div>
        )}

        <label className="login-field">
          <span>用户名</span>
          <input
            type="text"
            value={userId}
            onChange={(e) => setUserId(e.target.value)}
            placeholder="请输入用户名"
            autoFocus
            disabled={loading}
          />
        </label>

        <label className="login-field">
          <span>密码</span>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="请输入密码"
            disabled={loading}
          />
        </label>

        <button type="submit" className="button-primary login-button" disabled={loading}>
          {loading ? '登录中...' : '登录'}
        </button>
      </form>
    </div>
  )
}
