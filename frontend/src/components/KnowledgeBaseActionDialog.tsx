import { AlertTriangle, RotateCcw } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { api } from '../api/client'
import type { KnowledgeBase } from '../types'
import { Modal } from './Modal'

export type KnowledgeBaseAction = 'restore' | 'delete'

interface Props {
  knowledgeBase: KnowledgeBase | null
  action: KnowledgeBaseAction
  onClose: () => void
  onSuccess: (knowledgeBase: KnowledgeBase) => void
}

export function KnowledgeBaseActionDialog({ knowledgeBase, action, onClose, onSuccess }: Props) {
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const pending = useRef(false)
  useEffect(() => setError(''), [knowledgeBase?.id, action])

  async function handleConfirm() {
    if (!knowledgeBase || pending.current) return
    pending.current = true
    setSubmitting(true)
    setError('')
    try {
      const restored =
        action === 'restore'
          ? await api.restoreKnowledgeBase(knowledgeBase.id)
          : await api.permanentlyDeleteKnowledgeBase(knowledgeBase.id).then(() => knowledgeBase)
      onSuccess(restored)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '操作失败，请稍后重试')
    } finally {
      pending.current = false
      setSubmitting(false)
    }
  }

  const isDelete = action === 'delete'
  const Icon = isDelete ? AlertTriangle : RotateCcw
  return (
    <Modal
      open={knowledgeBase !== null}
      title={isDelete ? '彻底删除知识库' : '还原知识库'}
      onClose={() => !pending.current && onClose()}
      busy={submitting}
    >
      <div className="modal-body form-stack">
        <div className={`project-action-summary ${isDelete ? 'destructive' : ''}`}>
          <Icon size={23} aria-hidden="true" />
          <div>
            <strong>{knowledgeBase?.name || '未命名知识库'}</strong>
            <p>
              {isDelete
                ? '知识库及其全部文档和索引将被永久删除，此操作无法撤销。'
                : '知识库将恢复到知识库列表，文档和索引会一并保留。'}
            </p>
          </div>
        </div>
        {error && (
          <div className="form-message error" role="alert">
            {error}
          </div>
        )}
        <div className="modal-actions">
          <button className="secondary-button" type="button" onClick={onClose} disabled={submitting}>
            取消
          </button>
          <button
            className={isDelete ? 'primary-button destructive-button' : 'primary-button'}
            type="button"
            onClick={() => void handleConfirm()}
            disabled={submitting}
          >
            {submitting ? (isDelete ? '正在删除…' : '正在还原…') : isDelete ? '彻底删除' : '确认还原'}
          </button>
        </div>
      </div>
    </Modal>
  )
}
