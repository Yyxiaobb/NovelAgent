import { AlertTriangle, RotateCcw, Trash2 } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { api } from '../api/client'
import type { Project } from '../types'
import { Modal } from './Modal'

export type ProjectAction = 'recycle' | 'restore' | 'delete'

const labels = {
  recycle: { title: '移入回收站', confirm: '移入回收站', pending: '正在移入…', icon: Trash2 },
  restore: { title: '还原作品', confirm: '确认还原', pending: '正在还原…', icon: RotateCcw },
  delete: { title: '彻底删除作品', confirm: '彻底删除', pending: '正在删除…', icon: AlertTriangle },
}

interface ProjectActionDialogProps {
  project: Project | null
  action: ProjectAction
  onClose: () => void
  onSuccess: (project: Project) => void
}

export function ProjectActionDialog({ project, action, onClose, onSuccess }: ProjectActionDialogProps) {
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const pending = useRef(false)
  const { title, confirm, pending: pendingLabel, icon: Icon } = labels[action]

  useEffect(() => setError(''), [project?.id, action])

  function closeDialog() {
    if (!pending.current) onClose()
  }

  async function handleConfirm() {
    if (!project || pending.current) return
    pending.current = true
    setSubmitting(true)
    setError('')
    try {
      if (action === 'recycle') await api.recycleProject(project.id)
      else if (action === 'restore') await api.restoreProject(project.id)
      else await api.permanentlyDeleteProject(project.id)
      onSuccess(project)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '操作失败，请稍后重试')
    } finally {
      pending.current = false
      setSubmitting(false)
    }
  }

  return (
    <Modal open={project !== null} title={title} onClose={closeDialog} busy={submitting}>
      <div className="modal-body form-stack">
        <div className={`project-action-summary ${action === 'delete' ? 'destructive' : ''}`}>
          <Icon size={23} aria-hidden="true" />
          <div>
            <strong>{project?.projectname || '未命名作品'}</strong>
            <p>{action === 'recycle' ? '作品将从作品列表中移除，章节会保留，可随时在回收站还原。'
              : action === 'restore' ? '作品将回到作品列表，并恢复移入回收站前的状态。此前单独删除的章节仍留在回收站，需单独还原。早期删除的作品默认还原为连载中。'
              : '作品及其全部章节将被永久删除。此操作无法撤销，也无法再次还原，请确认后继续。'}</p>
          </div>
        </div>
        {error && <div className="form-message error" role="alert">{error}</div>}
        <div className="modal-actions">
          <button className="secondary-button" type="button" onClick={closeDialog} disabled={submitting}>取消</button>
          <button className={action === 'delete' ? 'primary-button destructive-button' : 'primary-button'} type="button" onClick={() => void handleConfirm()} disabled={submitting}>
            {submitting ? pendingLabel : confirm}
          </button>
        </div>
      </div>
    </Modal>
  )
}
