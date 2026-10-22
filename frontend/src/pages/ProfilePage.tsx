import { Camera, Pencil, Save, Upload, X } from 'lucide-react'
import { useEffect, useState, type FormEvent } from 'react'
import { useAuth } from '../auth/AuthContext'
import { api } from '../api/client'
import type { Gender } from '../types'

function readFileAsDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result))
    reader.onerror = () => reject(new Error('读取图片失败，请重试'))
    reader.readAsDataURL(file)
  })
}

export function ProfilePage() {
  const { user, updateProfile } = useAuth()
  const [nickname, setNickname] = useState('')
  const [avatar, setAvatar] = useState('')
  const [gender, setGender] = useState<Gender>('unknown')
  const [bio, setBio] = useState('')
  const [phone, setPhone] = useState('')
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [uploadingAvatar, setUploadingAvatar] = useState(false)
  const [editing, setEditing] = useState(false)

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
    if (!editing) return
    setSubmitting(true)
    setMessage(null)
    try {
      await updateProfile({ nickname, avatar, gender, bio, phone: phone || undefined })
      setMessage({ type: 'success', text: '个人资料已更新' })
      setEditing(false)
    } catch (reason) {
      setMessage({ type: 'error', text: reason instanceof Error ? reason.message : '保存失败，请稍后重试' })
    } finally {
      setSubmitting(false)
    }
  }

  function cancelEditing() {
    if (!user) return
    setNickname(user.nickname || '')
    setAvatar(user.avatar || '')
    setGender(user.gender || 'unknown')
    setBio(user.bio || '')
    setPhone(user.phone || '')
    setMessage(null)
    setEditing(false)
  }

  async function handleAvatarUpload(file?: File) {
    if (!file) return
    if (!file.type.startsWith('image/')) {
      setMessage({ type: 'error', text: '请选择图片文件' })
      return
    }
    if (file.size > 5 * 1024 * 1024) {
      setMessage({ type: 'error', text: '头像图片不能超过 5 MB' })
      return
    }
    setUploadingAvatar(true)
    setMessage(null)
    try {
      const dataUrl = await readFileAsDataUrl(file)
      const uploaded = await api.uploadAvatar(dataUrl, file.name)
      setAvatar(uploaded.avatar || '')
      setMessage({ type: 'success', text: '头像已选用，保存资料后生效' })
    } catch (reason) {
      setMessage({ type: 'error', text: reason instanceof Error ? reason.message : '头像上传失败，请稍后重试' })
    } finally {
      setUploadingAvatar(false)
    }
  }

  return (
    <div className="page narrow-page">
      <header className="page-header">
        <div>
          <p className="eyebrow">账户资料</p>
          <h1>个人资料</h1>
          <p>这些信息用于工作台中的账户展示。</p>
        </div>
        <div className="page-header-actions">
          {editing ? (
            <button className="secondary-button" type="button" onClick={cancelEditing} disabled={submitting}>
              <X size={16} />
              取消
            </button>
          ) : (
            <button className="primary-button" type="button" onClick={() => setEditing(true)}>
              <Pencil size={16} />
              修改资料
            </button>
          )}
        </div>
      </header>
      <form className="settings-panel" onSubmit={handleSubmit}>
        <div className="profile-identity">
          <div className="avatar-large-wrap">
            {avatar ? (
              <img className="avatar-large" src={avatar} alt="头像预览" />
            ) : (
              <span className="avatar-large avatar-fallback">{(nickname || user?.username || 'U').slice(0, 1)}</span>
            )}
            {editing && (
              <label className="avatar-camera" title="从本地上传头像">
                <Camera size={15} />
                <input
                  className="visually-hidden-file-input"
                  type="file"
                  accept="image/png,image/jpeg,image/webp,image/gif"
                  onChange={event => {
                    void handleAvatarUpload(event.target.files?.[0])
                    event.currentTarget.value = ''
                  }}
                  disabled={uploadingAvatar}
                  aria-label="从本地上传头像"
                />
              </label>
            )}
          </div>
          <div>
            <strong>{nickname || user?.username}</strong>
            <span>@{user?.username}</span>
          </div>
        </div>
        <div className="form-grid">
          <label className="field">
            <span>用户名</span>
            <input value={user?.username || ''} disabled />
            <small>用户名暂不支持修改</small>
          </label>
          <label className="field">
            <span>昵称</span>
            <input
              value={nickname}
              onChange={event => setNickname(event.target.value)}
              maxLength={50}
              placeholder="你的显示名称"
              disabled={!editing}
            />
          </label>
          <label className="field full-span">
            <span>头像地址或本地图片</span>
            <input
              type="url"
              value={avatar}
              onChange={event => setAvatar(event.target.value)}
              maxLength={255}
              placeholder="https://example.com/avatar.jpg，也可以点击头像角标上传"
              disabled={!editing}
            />
            <small>
              <Upload size={12} /> 支持 PNG、JPG、WEBP、GIF，单张不超过 5 MB
            </small>
          </label>
          <label className="field">
            <span>性别</span>
            <select value={gender} onChange={event => setGender(event.target.value as Gender)} disabled={!editing}>
              <option value="unknown">未设置</option>
              <option value="female">女</option>
              <option value="male">男</option>
            </select>
          </label>
          <label className="field">
            <span>手机号</span>
            <input
              value={phone}
              onChange={event => setPhone(event.target.value)}
              pattern="1[3456789]\d{9}"
              placeholder="选填"
              inputMode="tel"
              disabled={!editing}
            />
          </label>
          <label className="field full-span">
            <span>个人简介</span>
            <textarea
              value={bio}
              onChange={event => setBio(event.target.value)}
              maxLength={500}
              rows={5}
              placeholder="写一点关于你和你的创作"
              disabled={!editing}
            />
            <small>{bio.length}/500</small>
          </label>
        </div>
        {message && (
          <div className={`form-message ${message.type}`} role="status">
            {message.text}
          </div>
        )}
        {editing && (
          <div className="panel-actions">
            <button className="primary-button" type="submit" disabled={submitting || uploadingAvatar}>
              <Save size={17} />
              {submitting ? '正在保存…' : '保存资料'}
            </button>
          </div>
        )}
      </form>
    </div>
  )
}
