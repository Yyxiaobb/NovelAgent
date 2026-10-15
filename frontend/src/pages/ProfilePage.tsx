import { Camera, Save } from 'lucide-react'
import { useEffect, useState, type FormEvent } from 'react'
import { useAuth } from '../auth/AuthContext'
import type { Gender } from '../types'

export function ProfilePage() {
  const { user, updateProfile } = useAuth()
  const [nickname, setNickname] = useState('')
  const [avatar, setAvatar] = useState('')
  const [gender, setGender] = useState<Gender>('unknown')
  const [bio, setBio] = useState('')
  const [phone, setPhone] = useState('')
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null)
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    if (!user) return
    setNickname(user.nickname || '')
    setAvatar(user.avatar || '')
    setGender(user.gender || 'unknown')
    setBio(user.bio || '')
    setPhone(user.phone || '')
  }, [user])

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setSubmitting(true)
    setMessage(null)
    try {
      await updateProfile({ nickname, avatar, gender, bio, phone: phone || undefined })
      setMessage({ type: 'success', text: '个人资料已更新' })
    } catch (reason) {
      setMessage({ type: 'error', text: reason instanceof Error ? reason.message : '保存失败，请稍后重试' })
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="page narrow-page">
      <header className="page-header"><div><p className="eyebrow">账户资料</p><h1>个人资料</h1><p>这些信息用于工作台中的账户展示。</p></div></header>
      <form className="settings-panel" onSubmit={handleSubmit}>
        <div className="profile-identity">
          <div className="avatar-large-wrap">
            {avatar ? <img className="avatar-large" src={avatar} alt="头像预览" /> : <span className="avatar-large avatar-fallback">{(nickname || user?.username || 'U').slice(0, 1)}</span>}
            <span className="avatar-camera"><Camera size={15} /></span>
          </div>
          <div><strong>{nickname || user?.username}</strong><span>@{user?.username}</span></div>
        </div>
        <div className="form-grid">
          <label className="field"><span>用户名</span><input value={user?.username || ''} disabled /><small>用户名暂不支持修改</small></label>
          <label className="field"><span>昵称</span><input value={nickname} onChange={(event) => setNickname(event.target.value)} maxLength={50} placeholder="你的显示名称" /></label>
          <label className="field full-span"><span>头像地址</span><input type="url" value={avatar} onChange={(event) => setAvatar(event.target.value)} maxLength={255} placeholder="https://example.com/avatar.jpg" /></label>
          <label className="field"><span>性别</span><select value={gender} onChange={(event) => setGender(event.target.value as Gender)}><option value="unknown">未设置</option><option value="female">女</option><option value="male">男</option></select></label>
          <label className="field"><span>手机号</span><input value={phone} onChange={(event) => setPhone(event.target.value)} pattern="1[3456789]\d{9}" placeholder="选填" inputMode="tel" /></label>
          <label className="field full-span"><span>个人简介</span><textarea value={bio} onChange={(event) => setBio(event.target.value)} maxLength={500} rows={5} placeholder="写一点关于你和你的创作" /><small>{bio.length}/500</small></label>
        </div>
        {message && <div className={`form-message ${message.type}`} role="status">{message.text}</div>}
        <div className="panel-actions"><button className="primary-button" type="submit" disabled={submitting}><Save size={17} />{submitting ? '正在保存…' : '保存资料'}</button></div>
      </form>
    </div>
  )
}
