import { Eye, EyeOff, KeyRound, LogOut, ShieldCheck, X } from 'lucide-react'
import { useEffect, useState, type FormEvent } from 'react'
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
  const [changingPassword, setChangingPassword] = useState(false)
  const [reviewConfig, setReviewConfig] = useState<Awaited<ReturnType<typeof api.getReviewConfig>> | null>(null)
  const [reviewStats, setReviewStats] = useState<Awaited<ReturnType<typeof api.getReviewStats>> | null>(null)
  const [reviewForm, setReviewForm] = useState({ enabled: false, max_rounds: 3, accept_score: 85, manual_approval: false })
  const [savingReview, setSavingReview] = useState(false)
  const [reviewConfigError, setReviewConfigError] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    void Promise.all([api.getReviewPreferences(), api.getReviewStats()])
      .then(([config, stats]) => {
        if (active) {
          setReviewConfig(config)
          setReviewStats(stats)
          setReviewForm({
            enabled: config.enabled,
            max_rounds: config.max_rounds,
            accept_score: config.accept_score,
            manual_approval: config.manual_approval,
          })
        }
      })
      .catch(reason => {
        if (active) setReviewConfigError(reason instanceof Error ? reason.message : '评审信息读取失败')
      })
    return () => {
      active = false
    }
  }, [])

  async function saveReviewPreferences(event: FormEvent) {
    event.preventDefault()
    setSavingReview(true)
    setReviewConfigError(null)
    try {
      const saved = await api.updateReviewPreferences(reviewForm)
      setReviewConfig(saved)
    } catch (reason) {
      setReviewConfigError(reason instanceof Error ? reason.message : '评审偏好保存失败')
    } finally {
      setSavingReview(false)
    }
  }

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
          {!changingPassword ? (
            <button className="secondary-button" type="button" onClick={() => setChangingPassword(true)}>
              <KeyRound size={16} />
              修改密码
            </button>
          ) : (
            <button
              className="secondary-button"
              type="button"
              onClick={() => {
                setChangingPassword(false)
                setMessage(null)
              }}
              disabled={submitting}
            >
              <X size={16} />
              取消
            </button>
          )}
        </div>
        {changingPassword && (
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
        )}
      </section>
      <section className="settings-panel">
        <div className="panel-title">
          <span className="panel-title-icon neutral">
            <ShieldCheck size={19} />
          </span>
          <div>
            <h2>章节评审</h2>
            <p>查看当前服务端的评论员运行配置，密钥和地址不会在页面展示。</p>
          </div>
        </div>
        {reviewConfigError && <div className="form-message error" role="status">{reviewConfigError}</div>}
        {reviewConfig && (
          <>
          <div className="review-config-grid">
            <div><span>状态</span><strong>{reviewConfig.enabled ? '已启用' : '未启用'}</strong></div>
            <div><span>最多轮数</span><strong>{reviewConfig.max_rounds} 轮</strong></div>
            <div><span>达标分数</span><strong>{reviewConfig.accept_score} 分</strong></div>
            <div>
              <span>评论员模型</span>
              <strong>
                {reviewConfig.reviewer_mode === 'shared'
                  ? '复用正文模型'
                  : reviewConfig.reviewer_model || '独立模型'}
              </strong>
            </div>
            {reviewConfig.configuration_status === 'incomplete' && (
              <p className="settings-inline-warning">独立评论员配置不完整，将无法正常启动评审。</p>
            )}
          </div>
          <form className="form-stack settings-form review-preferences-form" onSubmit={saveReviewPreferences}>
            <label className="field"><span>账户默认</span>
              <select value={reviewForm.enabled ? 'on' : 'off'} onChange={event => setReviewForm(value => ({ ...value, enabled: event.target.value === 'on' }))}>
                <option value="off">关闭评论员</option><option value="on">启用评论员</option>
              </select>
            </label>
            <label className="field"><span>最大评审轮数（1–3）</span>
              <input type="number" min="1" max="3" value={reviewForm.max_rounds} onChange={event => setReviewForm(value => ({ ...value, max_rounds: Number(event.target.value) }))} />
            </label>
            <label className="field"><span>达标分数（0–100）</span>
              <input type="number" min="0" max="100" value={reviewForm.accept_score} onChange={event => setReviewForm(value => ({ ...value, accept_score: Number(event.target.value) }))} />
            </label>
            <label className="checkbox-field">
              <input type="checkbox" checked={reviewForm.manual_approval} onChange={event => setReviewForm(value => ({ ...value, manual_approval: event.target.checked }))} />
              <span>人工审核模式：生成初稿和评审意见后停止，等待我手动修改或确认，不自动应用 AI 修订</span>
            </label>
            <button className="primary-button" type="submit" disabled={savingReview}>{savingReview ? '正在保存…' : '保存账户默认'}</button>
          </form>
          </>
        )}
      </section>
      <section className="settings-panel">
        <div className="panel-title">
          <span className="panel-title-icon neutral"><ShieldCheck size={19} /></span>
          <div>
            <h2>评审质量统计</h2>
            <p>基于最近最多 5000 条正文生成任务；评分和耗时只统计已完成评审的任务。</p>
          </div>
        </div>
        {reviewStats && (
          <div className="review-config-grid">
            <div><span>正文生成任务</span><strong>{reviewStats.total_jobs}</strong></div>
            <div><span>完成评审</span><strong>{reviewStats.reviewed_jobs}</strong></div>
            <div><span>平均评分</span><strong>{reviewStats.average_score ?? '暂无'}{reviewStats.average_score === null ? '' : ' 分'}</strong></div>
            <div><span>平均评审轮数</span><strong>{reviewStats.average_rounds ?? '暂无'}{reviewStats.average_rounds === null ? '' : ' 轮'}</strong></div>
            <div><span>平均任务耗时</span><strong>{reviewStats.average_duration_seconds ?? '暂无'}{reviewStats.average_duration_seconds === null ? '' : ' 秒'}</strong></div>
            <div><span>评论员不可用</span><strong>{reviewStats.review_unavailable_jobs}</strong></div>
            <div>
              <span>修订决策</span>
              <strong>
                采纳 {reviewStats.revision_decisions.accepted ?? 0} · 部分采纳 {reviewStats.revision_decisions.partially_accepted ?? 0} · 拒绝 {reviewStats.revision_decisions.rejected ?? 0}
              </strong>
            </div>
          </div>
        )}
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
