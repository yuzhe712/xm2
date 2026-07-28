import { FormEvent, useEffect, useState } from 'react'
import { Navigate, useLocation, useNavigate } from 'react-router-dom'

import { ROLE_HOME } from '../app/ProtectedRoute'
import { useAuth } from '../app/AuthProvider'

export function LoginPage(): JSX.Element {
  const auth = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')

  useEffect(() => {
    if (!auth.user) return
    const from = (location.state as { from?: string } | null)?.from
    navigate(from && from !== '/login' ? from : ROLE_HOME[auth.user.role], { replace: true })
  }, [auth.user, location.state, navigate])

  if (auth.user && !auth.loading) return <Navigate to={ROLE_HOME[auth.user.role]} replace />

  const submit = (event: FormEvent) => {
    event.preventDefault()
    if (username.trim() && password) void auth.login(username.trim(), password)
  }

  return (
    <main className="login-page">
      <section className="login-intro">
        <div className="brand-block login-brand"><span className="brand-mark">IT</span><div><strong>IntelliTicket</strong><span>内部 IT 服务台</span></div></div>
        <div><span className="eyebrow">统一服务入口</span><h1>让每一项请求都有清晰的负责人和处理记录</h1><p>提交问题、跟进处理进展，并在解决后完成确认。</p></div>
      </section>
      <form className="login-form" onSubmit={submit}>
        <header><h2>登录</h2><p>使用组织分配的账号进入对应工作区。</p></header>
        {auth.error && <div className="error-banner" role="alert">{auth.error}</div>}
        <label><span>用户名</span><input aria-label="用户名" autoComplete="username" value={username} onChange={(event) => setUsername(event.target.value)} /></label>
        <label><span>密码</span><input aria-label="密码" type="password" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} /></label>
        <button type="submit" disabled={auth.loading || !username.trim() || !password}>{auth.loading ? '正在登录...' : '登录'}</button>
      </form>
    </main>
  )
}
