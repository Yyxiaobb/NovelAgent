import { AlertTriangle, RotateCcw, Trash2 } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { api } from '../api/client'
import type { Chapter } from '../types'
import { Modal } from './Modal'

export type ChapterAction = 'recycle' | 'restore' | 'delete'

const labels = {
  recycle: { title: '移入回收站', confirm: '移入回收站', pending: '正在移入…', icon: Trash2 },
  restore: { title: '还原章节', confirm: '确认还原', pending: '正在还原…', icon: RotateCcw },
  delete: { title: '彻底删除章节', confirm: '彻底删除', pending: '正在删除…', icon: AlertTriangle },
}

interface ChapterActionDialogProps {
  chapter: Chapter | null
  action: ChapterAction
  onClose: () => void
  onSuccess: (chapter: Chapter) => void
}

function chapterTitle(chapter: Chapter | null) {
  return chapter?.chaptername || `第 ${chapter?.chapter_number ?? ''} 章`
}

export function ChapterActionDialog({ chapter, action, onClose, onSuccess }: ChapterActionDialogProps) {
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const pending = useRef(false)
  const { title, confirm, pending: pendingLabel, icon: Icon } = labels[action]

  useEffect(() => setError(''), [chapter?.id, action])

  function closeDialog() {
    if (!pending.current) onClose()
  }

  async function handleConfirm() {
    if (!chapter || pending.current) return
    pending.current = true
    setSubmitting(true)
    setError('')
    try {
      if (action === 'recycle') await api.recycleChapter(chapter.id)
      else if (action === 'restore') await api.restoreChapter(chapter.id)
      else await api.permanentlyDeleteChapter(chapter.id)
      onSuccess(chapter)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '操作失败，请稍后重试')
    } finally {
      pending.current = false
      setSubmitting(false)
    }
  }

  return (
    <Modal open={chapter !== null} title={title} onClose={closeDialog} busy={submitting}>
      <div className="modal-body form-stack">
        <div className={`project-action-summary ${action === 'delete' ? 'destructive' : ''}`}>
          <Icon size={23} aria-hidden="true" />
          <div>
            <strong>{chapterTitle(chapter)}</strong>
            <p>{action === 'recycle' ? '本章会从作品章节列表中移除，章节数据保留，可在回收站单独还原。'
              : action === 'restore' ? '本章会以原有编号回到所属作品的章节列表。'
              : '本章数据将被永久删除。此操作无法撤销，请确认后继续。'}</p>
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
