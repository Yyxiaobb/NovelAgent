import { BookOpenText, CalendarDays, FileText, Plus, Search } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState, type FormEvent } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api } from '../api/client'
import { Modal } from '../components/Modal'
import type { Project } from '../types'

const numberFormat = new Intl.NumberFormat('zh-CN')
const dateFormat = new Intl.DateTimeFormat('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' })

export function ProjectsPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [projects, setProjects] = useState<Project[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [query, setQuery] = useState('')
  const [name, setName] = useState('')
  const [introduction, setIntroduction] = useState('')
  const [submitError, setSubmitError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const modalOpen = searchParams.get('create') === '1'

  const loadProjects = useCallback(() => {
    setLoading(true)
    setError('')
    api.getProjects().then(setProjects).catch((reason) => setError(reason.message)).finally(() => setLoading(false))
  }, [])

  useEffect(loadProjects, [loadProjects])

  const filteredProjects = useMemo(() => {
    const keyword = query.trim().toLowerCase()
    if (!keyword) return projects
    return projects.filter((project) => `${project.projectname || ''} ${project.introduction || ''}`.toLowerCase().includes(keyword))
  }, [projects, query])

  function closeModal() {
    setSearchParams({}, { replace: true })
    setSubmitError('')
  }

  async function handleCreate(event: FormEvent) {
    event.preventDefault()
    setSubmitting(true)
    setSubmitError('')
    try {
      const project = await api.createProject(name.trim(), introduction.trim())
      setProjects((current) => [project, ...current])
      setName('')
      setIntroduction('')
      closeModal()
    } catch (reason) {
      setSubmitError(reason instanceof Error ? reason.message : '创建失败，请稍后重试')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="page">
      <header className="page-header"><div><p className="eyebrow">作品管理</p><h1>我的作品</h1><p>集中查看小说项目与创作进度。</p></div><button className="primary-button" onClick={() => setSearchParams({ create: '1' })}><Plus size={17} />新建作品</button></header>

      <div className="toolbar">
        <label className="search-box"><Search size={17} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索作品名称或简介" aria-label="搜索作品" /></label>
        <span className="result-count">共 {filteredProjects.length} 部作品</span>
      </div>

      {error ? <div className="empty-state"><p>{error}</p><button className="secondary-button" onClick={loadProjects}>重新加载</button></div>
        : loading ? <div className="project-grid skeleton-grid"><span /><span /><span /></div>
        : filteredProjects.length === 0 ? (
          <div className="empty-state"><BookOpenText size={32} /><h3>{query ? '没有匹配的作品' : '作品集还是空的'}</h3><p>{query ? '换一个关键词试试。' : '创建作品后，可在这里查看创作进度。'}</p>{!query && <button className="primary-button" onClick={() => setSearchParams({ create: '1' })}><Plus size={17} />新建作品</button>}</div>
        ) : (
          <div className="project-grid">
            {filteredProjects.map((project) => (
              <article className="project-card" key={project.id}>
                <div className="project-card-top"><span className="project-monogram">{(project.projectname || '未').slice(0, 1)}</span><span className={`status-badge ${project.status === '完结' ? 'done' : project.status === '断更' ? 'paused' : ''}`}>{project.status}</span></div>
                <h2>{project.projectname || '未命名作品'}</h2>
                <p>{project.introduction || '尚未填写作品简介'}</p>
                <div className="project-stats"><span><FileText size={15} />{project.chapter_count} 章</span><span>{numberFormat.format(project.total_words)} 字</span></div>
                <div className="project-updated"><CalendarDays size={14} />更新于 {dateFormat.format(new Date(project.updated_at))}</div>
              </article>
            ))}
          </div>
        )}

      <Modal open={modalOpen} title="新建作品" onClose={closeModal}>
        <form className="modal-body form-stack" onSubmit={handleCreate}>
          <label className="field"><span>作品名称</span><input value={name} onChange={(event) => setName(event.target.value)} minLength={2} maxLength={20} placeholder="例如：雾港来信" autoFocus required /><small>{name.length}/20</small></label>
          <label className="field"><span>作品简介</span><textarea value={introduction} onChange={(event) => setIntroduction(event.target.value)} maxLength={500} rows={5} placeholder="简要描述故事背景、主角或核心冲突" /><small>{introduction.length}/500</small></label>
          {submitError && <div className="form-message error" role="alert">{submitError}</div>}
          <div className="modal-actions"><button className="secondary-button" type="button" onClick={closeModal}>取消</button><button className="primary-button" type="submit" disabled={submitting}>{submitting ? '正在创建…' : '创建作品'}</button></div>
        </form>
      </Modal>
    </div>
  )
}
