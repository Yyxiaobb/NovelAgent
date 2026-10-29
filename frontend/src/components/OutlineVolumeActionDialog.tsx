import { AlertTriangle, RotateCcw } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { api } from '../api/client'
import type { RecycledOutlineVolume } from '../types'
import { Modal } from './Modal'

export type OutlineVolumeAction = 'restore' | 'delete'

interface Props {
  volume: RecycledOutlineVolume | null
  action: OutlineVolumeAction
  onClose: () => void
  onSuccess: (volume: RecycledOutlineVolume) => void
}

export function OutlineVolumeActionDialog({ volume, action, onClose, onSuccess }: Props) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const pending = useRef(false)
  const destructive = action === 'delete'
  const Icon = destructive ? AlertTriangle : RotateCcw
  useEffect(() => setError(''), [volume?.id, action])

  async function confirm() {
    if (!volume || pending.current) return
    pending.current = true
    setBusy(true)
    setError('')
    try {
      if (destructive) await api.permanentlyDeleteOutlineVolume(volume.id)
      else await api.restoreOutlineVolume(volume.id)
      onSuccess(volume)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '操作失败，请稍后重试')
    } finally {
      pending.current = false
      setBusy(false)
    }
  }

  return (
    <Modal
      open={volume !== null}
      title={destructive ? '彻底删除卷纲' : '还原卷纲'}
      onClose={() => !pending.current && onClose()}
      busy={busy}
    >
      <div className="modal-body form-stack">
        <div className={`project-action-summary ${destructive ? 'destructive' : ''}`}>
          <Icon size={23} aria-hidden="true" />
          <div>
            <strong>{volume?.name || '未命名卷纲'}</strong>
            <p>
              {destructive
                ? '卷纲将被永久删除，此操作无法撤销。'
                : volume?.project_status === '回收站'
                  ? '请先还原所属作品，再还原此卷纲。'
                  : '卷纲将回到所属作品的大纲详情页。'}
            </p>
          </div>
        </div>
        {error && <div className="form-message error" role="alert">{error}</div>}
        <div className="modal-actions">
          <button className="secondary-button" type="button" onClick={onClose} disabled={busy}>取消</button>
          <button
            className={destructive ? 'primary-button destructive-button' : 'primary-button'}
            type="button"
            onClick={() => void confirm()}
            disabled={busy || (!destructive && volume?.project_status === '回收站')}
          >
            {busy ? (destructive ? '正在删除…' : '正在还原…') : destructive ? '彻底删除' : '确认还原'}
          </button>
        </div>
      </div>
    </Modal>
  )
}
