import { Bot, Plus, Save, Sparkles } from 'lucide-react'
import { useEffect, useState, type FormEvent } from 'react'
import { api } from '../api/client'
import type { Project } from '../types'
import { Modal } from './Modal'

const projectTypes = ['玄幻', '都市', '言情', '悬疑', '科幻', '历史', '武侠', '现实', '灵异', '同人', '儿童', '其他']

interface ProjectCreationModalProps {
  open: boolean
  onClose: () => void
  onCreated: (project: Project) => void
  draftKey?: string
}

type Field = 'projectname' | 'introduction' | 'project_type'

interface ProjectDraft {
  name: string
  introduction: string
  projectType: string
}

const DEFAULT_DRAFT_KEY = 'anonymous'

export function ProjectCreationModal({
  open,
  onClose,
  onCreated,
  draftKey = DEFAULT_DRAFT_KEY,
}: ProjectCreationModalProps) {
  const [name, setName] = useState('')
  const [introduction, setIntroduction] = useState('')
  const [projectType, setProjectType] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [generating, setGenerating] = useState<Field | null>(null)
  const [error, setError] = useState('')
  const [draftNotice, setDraftNotice] = useState('')
  const storageKey = `novel-agent-project-draft:${draftKey}`

  useEffect(() => {
    if (!open) return
    setError('')
    setDraftNotice('')
    try {
      const saved = localStorage.getItem(storageKey)
      if (!saved) return
      const draft = JSON.parse(saved) as Partial<ProjectDraft>
      setName(typeof draft.name === 'string' ? draft.name : '')
      setIntroduction(typeof draft.introduction === 'string' ? draft.introduction : '')
      setProjectType(typeof draft.projectType === 'string' ? draft.projectType : '')
    } catch {
      localStorage.removeItem(storageKey)
    }
  }, [open, storageKey])

  function reset() {
    setName('')
    setIntroduction('')
    setProjectType('')
    setError('')
    setDraftNotice('')
    setGenerating(null)
    setSubmitting(false)
  }

  function close() {
    if (submitting || generating) return
    reset()
    onClose()
  }

  function saveDraft() {
    try {
      const draft: ProjectDraft = { name, introduction, projectType }
      localStorage.setItem(storageKey, JSON.stringify(draft))
      setDraftNotice('草稿已保存，下次打开时会自动恢复。')
      setError('')
    } catch {
      setError('草稿保存失败，请检查浏览器存储空间或隐私设置')
    }
  }

  async function generate(field: Field) {
    setGenerating(field)
    setError('')
    try {
      const result = await api.generateProjectField({
        field,
        projectname: name.trim() || undefined,
        introduction: introduction.trim() || undefined,
        project_type: projectType || undefined,
      })
      if (field === 'projectname') setName(result.value.slice(0, 20))
      if (field === 'introduction') setIntroduction(result.value.slice(0, 500))
      if (field === 'project_type') setProjectType(projectTypes.includes(result.value) ? result.value : '其他')
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '智能生成失败，请稍后重试')
    } finally {
      setGenerating(null)
    }
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setSubmitting(true)
    setError('')
    try {
      const project = await api.createProject(name.trim(), introduction.trim(), projectType)
      localStorage.removeItem(storageKey)
      onCreated(project)
      reset()
      onClose()
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '创建失败，请稍后重试')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Modal open={open} title="新建作品" onClose={close} busy={submitting || Boolean(generating)}>
      <form className="modal-body form-stack project-creation-form" onSubmit={handleSubmit}>
        <p className="creation-intro">
          <Bot size={17} />
          填写作品设定，智能体可以协助你快速生成灵感。
        </p>
        <label className="field">
          <span>作品名称</span>
          <span className="field-with-action">
            <input
              value={name}
              onChange={event => setName(event.target.value)}
              minLength={2}
              maxLength={20}
              placeholder="例如：雾港来信"
              autoFocus
              required
            />
            <button
              className="ai-field-button"
              type="button"
              onClick={() => void generate('projectname')}
              disabled={submitting || Boolean(generating)}
              aria-label="智能生成作品名称"
              title="智能生成作品名称"
            >
              <Sparkles size={15} />
              智能生成
            </button>
          </span>
          <small>{name.length}/20</small>
        </label>
        <label className="field">
          <span>作品类型</span>
          <span className="field-with-action">
            <select value={projectType} onChange={event => setProjectType(event.target.value)} required>
              <option value="">请选择作品类型</option>
              {projectTypes.map(type => (
                <option key={type} value={type}>
                  {type}
                </option>
              ))}
            </select>
            <button
              className="ai-field-button"
              type="button"
              onClick={() => void generate('project_type')}
              disabled={submitting || Boolean(generating)}
              aria-label="智能生成作品类型"
              title="智能生成作品类型"
            >
              <Sparkles size={15} />
              智能生成
            </button>
          </span>
        </label>
        <label className="field">
          <span>作品简介</span>
          <span className="field-with-action textarea-with-action">
            <textarea
              value={introduction}
              onChange={event => setIntroduction(event.target.value)}
              maxLength={500}
              rows={5}
              placeholder="简要描述故事背景、主角或核心冲突"
            />
            <button
              className="ai-field-button"
              type="button"
              onClick={() => void generate('introduction')}
              disabled={submitting || Boolean(generating)}
              aria-label="智能生成作品简介"
              title="智能生成作品简介"
            >
              <Sparkles size={15} />
              智能生成
            </button>
          </span>
          <small>{introduction.length}/500</small>
        </label>
        {error && (
          <div className="form-message error" role="alert">
            {error}
          </div>
        )}
        {draftNotice && (
          <div className="form-message success" role="status">
            {draftNotice}
          </div>
        )}
        <div className="modal-actions">
          <button
            className="secondary-button"
            type="button"
            onClick={saveDraft}
            disabled={submitting || Boolean(generating)}
          >
            <Save size={16} />
            保存草稿
          </button>
          <button
            className="secondary-button"
            type="button"
            onClick={close}
            disabled={submitting || Boolean(generating)}
          >
            取消
          </button>
          <button className="primary-button" type="submit" disabled={submitting || Boolean(generating)}>
            <Plus size={17} />
            {submitting ? '正在创建…' : '创建作品'}
          </button>
        </div>
      </form>
    </Modal>
  )
}
