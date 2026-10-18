import { BookOpen, Eye, EyeOff, Feather } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { Navigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'

export function AuthPage() {
  const { user, login, register } = useAuth()
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  if (user) return <Navigate to="/" replace />

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setError('')
    if (mode === 'register' && password !== confirmPassword) {
      setError('两次输入的密码不一致')
      return
    }
    setSubmitting(true)
    try {
      await (mode === 'login' ? login(username, password) : register(username, password))
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '操作失败，请稍后重试')
    } finally {
      setSubmitting(false)
    }
  }

  function changeMode(nextMode: 'login' | 'register') {
    setMode(nextMode)
    setError('')
    setConfirmPassword('')
  }

  return (
    <main className="auth-page">
      <section className="auth-intro">
        <div className="auth-brand">
          <BookOpen size={22} />
          <span>墨笺</span>
        </div>
        <div className="auth-statement">
          <Feather size={30} />
          <h1>
            让每一个故事
            <br />
            都有落笔之处
          </h1>
          <p>整理作品，记录进度，把注意力留给真正重要的文字。</p>
        </div>
        <small>Novel workspace · 2026</small>
      </section>

      <section className="auth-form-side">
        <div className="auth-form-wrap">
          <div className="segmented-control" aria-label="账户操作">
            <button type="button" className={mode === 'login' ? 'active' : ''} onClick={() => changeMode('login')}>
              登录
            </button>
            <button
              type="button"
              className={mode === 'register' ? 'active' : ''}
              onClick={() => changeMode('register')}
            >
              注册
            </button>
          </div>
          <div className="auth-heading">
            <h2>{mode === 'login' ? '欢迎回来' : '创建写作账户'}</h2>
            <p>{mode === 'login' ? '继续你的创作进程。' : '从第一部作品开始，建立你的故事世界。'}</p>
          </div>
          <form className="form-stack" onSubmit={handleSubmit}>
            <label className="field">
              <span>用户名</span>
              <input
                value={username}
                onChange={event => setUsername(event.target.value)}
                minLength={3}
                maxLength={50}
                placeholder="请输入用户名"
                autoComplete="username"
                required
              />
            </label>
            <label className="field">
              <span>密码</span>
              <span className="input-with-action">
                <input
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={event => setPassword(event.target.value)}
                  minLength={mode === 'login' ? 5 : 6}
                  maxLength={128}
                  placeholder="请输入密码"
                  autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
                  required
                />
                <button
                  type="button"
                  className="input-action"
                  onClick={() => setShowPassword(value => !value)}
                  aria-label={showPassword ? '隐藏密码' : '显示密码'}
                >
                  {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                </button>
              </span>
            </label>
            {mode === 'register' && (
              <label className="field">
                <span>确认密码</span>
                <input
                  type={showPassword ? 'text' : 'password'}
                  value={confirmPassword}
                  onChange={event => setConfirmPassword(event.target.value)}
                  minLength={6}
                  maxLength={128}
                  placeholder="再次输入密码"
                  autoComplete="new-password"
                  required
                />
              </label>
            )}
            {error && (
              <div className="form-message error" role="alert">
                {error}
              </div>
            )}
            <button className="primary-button full-width" type="submit" disabled={submitting}>
              {submitting ? '正在处理…' : mode === 'login' ? '进入工作台' : '创建账户'}
            </button>
          </form>
        </div>
      </section>
    </main>
  )
}
