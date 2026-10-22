import { AlertTriangle, RotateCcw } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { api } from '../api/client'
import type { Inspiration } from '../types'
import { Modal } from './Modal'

export type InspirationAction = 'restore' | 'delete'

interface Props {
  inspiration: Inspiration | null
  action: InspirationAction
  onClose: () => void
  onSuccess: (inspiration: Inspiration) => void
}

export function InspirationActionDialog({ inspiration, action, onClose, onSuccess }: Props) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const pending = useRef(false)
  useEffect(() => setError(''), [inspiration?.id, action])

  async function confirm() {
    if (!inspiration || pending.current) return
    pending.current = true
    setBusy(true)
    setError('')
    try {
      const result =
        action === 'restore'
          ? await api.restoreInspiration(inspiration.id)
          : await api.permanentlyDeleteInspiration(inspiration.id).then(() => inspiration)
      onSuccess(result)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '操作失败，请稍后重试')
    } finally {
      pending.current = false
      setBusy(false)
    }
  }

  const destructive = action === 'delete'
  const Icon = destructive ? AlertTriangle : RotateCcw
  return (
    <Modal
      open={inspiration !== null}
      title={destructive ? '彻底删除灵感' : '还原灵感'}
      onClose={() => !pending.current && onClose()}
      busy={busy}
    >
      <div className="modal-body form-stack">
        <div className={`project-action-summary ${destructive ? 'destructive' : ''}`}>
          <Icon size={23} aria-hidden="true" />
          <div>
            <strong>{inspiration?.title || '未命名灵感'}</strong>
            <p>{destructive ? '灵感内容将被永久删除，此操作无法撤销。' : '灵感将回到灵感库，可以继续编辑和完善。'}</p>
          </div>
        </div>
        {error && (
          <div className="form-message error" role="alert">
            {error}
          </div>
        )}
        <div className="modal-actions">
          <button className="secondary-button" type="button" onClick={onClose} disabled={busy}>
            取消
          </button>
          <button
            className={destructive ? 'primary-button destructive-button' : 'primary-button'}
            type="button"
            onClick={() => void confirm()}
            disabled={busy}
          >
            {busy ? (destructive ? '正在删除…' : '正在还原…') : destructive ? '彻底删除' : '确认还原'}
          </button>
        </div>
      </div>
    </Modal>
  )
}
