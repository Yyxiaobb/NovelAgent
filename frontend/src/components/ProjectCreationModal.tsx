import { Plus } from 'lucide-react'
import { useEffect, useState, type FormEvent } from 'react'
import { api } from '../api/client'
import type { Project } from '../types'
import { Modal } from './Modal'

const projectTypes = ['玄幻', '都市', '言情', '悬疑', '科幻', '历史', '武侠', '现实', '灵异', '同人', '儿童', '其他']

interface ProjectCreationModalProps {
  open: boolean
  onClose: () => void
  onCreated: (project: Project) => void
}

export function ProjectCreationModal({
  open,
  onClose,
  onCreated,
}: ProjectCreationModalProps) {
  const [projectType, setProjectType] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!open) return
    setError('')
    setProjectType('')
  }, [open])

  function reset() {
    setProjectType('')
    setError('')
    setSubmitting(false)
  }

  function close() {
    if (submitting) return
    reset()
    onClose()
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setSubmitting(true)
    setError('')
    try {
      const project = await api.createProject(projectType)
      onClose()
      onCreated(project)
      reset()
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '创建失败，请稍后重试')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Modal open={open} title="新建作品" onClose={close} busy={submitting}>
      <form className="modal-body form-stack project-creation-form" onSubmit={handleSubmit}>
        <label className="field">
          <span>作品类型</span>
          <select value={projectType} onChange={event => setProjectType(event.target.value)} required autoFocus>
            <option value="">请选择作品类型</option>
            {projectTypes.map(type => (
              <option key={type} value={type}>
                {type}
              </option>
            ))}
          </select>
        </label>
        {error && (
          <div className="form-message error" role="alert">
            {error}
          </div>
        )}
        <div className="modal-actions">
          <button
            className="secondary-button"
            type="button"
            onClick={close}
            disabled={submitting}
          >
            取消
          </button>
          <button className="primary-button" type="submit" disabled={submitting}>
            <Plus size={17} />
            {submitting ? '正在创建…' : '创建作品'}
          </button>
        </div>
      </form>
    </Modal>
  )
}
