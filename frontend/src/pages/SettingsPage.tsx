import { Eye, EyeOff, KeyRound, LogOut, ShieldCheck } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { useAuth } from '../auth/AuthContext'
import { api } from '../api/client'

export function SettingsPage() {
  const { logout } = useAuth()
  const [oldPassword, setOldPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [visible, setVisible] = useState(false)
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null)
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setMessage(null)
    if (newPassword !== confirmPassword) {
      setMessage({ type: 'error', text: '两次输入的新密码不一致' })
      return
    }
    setSubmitting(true)
    try {
      await api.changePassword(oldPassword, newPassword)
      setOldPassword('')
      setNewPassword('')
      setConfirmPassword('')
      setMessage({ type: 'success', text: '密码修改成功' })
    } catch (reason) {
      setMessage({ type: 'error', text: reason instanceof Error ? reason.message : '修改失败，请稍后重试' })
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="page narrow-page">
      <header className="page-header">
        <div>
          <p className="eyebrow">账户设置</p>
          <h1>安全与登录</h1>
          <p>管理密码和当前登录状态。</p>
        </div>
      </header>
      <section className="settings-panel">
        <div className="panel-title">
          <span className="panel-title-icon">
            <KeyRound size={19} />
          </span>
          <div>
            <h2>修改密码</h2>
            <p>建议使用至少 8 位且不与其他服务重复的密码。</p>
          </div>
        </div>
        <form className="form-stack settings-form" onSubmit={handleSubmit}>
          <label className="field">
            <span>原密码</span>
            <input
              type={visible ? 'text' : 'password'}
              value={oldPassword}
              onChange={event => setOldPassword(event.target.value)}
              autoComplete="current-password"
              required
            />
          </label>
          <label className="field">
            <span>新密码</span>
            <span className="input-with-action">
              <input
                type={visible ? 'text' : 'password'}
                value={newPassword}
                onChange={event => setNewPassword(event.target.value)}
                minLength={6}
                maxLength={128}
                autoComplete="new-password"
                required
              />
              <button
                className="input-action"
                type="button"
                onClick={() => setVisible(value => !value)}
                aria-label={visible ? '隐藏密码' : '显示密码'}
              >
                {visible ? <EyeOff size={18} /> : <Eye size={18} />}
              </button>
            </span>
          </label>
          <label className="field">
            <span>确认新密码</span>
            <input
              type={visible ? 'text' : 'password'}
              value={confirmPassword}
              onChange={event => setConfirmPassword(event.target.value)}
              minLength={6}
              maxLength={128}
              autoComplete="new-password"
              required
            />
          </label>
          {message && (
            <div className={`form-message ${message.type}`} role="status">
              {message.text}
            </div>
          )}
          <div>
            <button className="primary-button" type="submit" disabled={submitting}>
              <ShieldCheck size={17} />
              {submitting ? '正在修改…' : '更新密码'}
            </button>
          </div>
        </form>
      </section>
      <section className="settings-panel danger-panel">
        <div className="panel-title">
          <span className="panel-title-icon neutral">
            <LogOut size={19} />
          </span>
          <div>
            <h2>退出当前账户</h2>
            <p>退出后，本机保存的登录凭证将被清除。</p>
          </div>
          <button className="secondary-button danger-button" onClick={() => void logout()}>
            <LogOut size={17} />
            退出登录
          </button>
        </div>
      </section>
    </div>
  )
}
