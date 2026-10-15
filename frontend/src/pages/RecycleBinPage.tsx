import { ArrowLeft, CalendarDays, FileText, RotateCcw, Search, Trash2 } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState, type KeyboardEvent } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import { ChapterActionDialog, type ChapterAction } from '../components/ChapterActionDialog'
import { ProjectActionDialog, type ProjectAction } from '../components/ProjectActionDialog'
import type { Chapter, Project, RecycledChapter } from '../types'

const numberFormat = new Intl.NumberFormat('zh-CN')
const dateFormat = new Intl.DateTimeFormat('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' })
type Tab = 'projects' | 'chapters'
type Selection =
  | { kind: 'project'; item: Project; action: ProjectAction }
  | { kind: 'chapter'; item: RecycledChapter; action: ChapterAction }

function chapterTitle(chapter: Chapter) {
  return chapter.chaptername || `第 ${chapter.chapter_number} 章`
}

export function RecycleBinPage() {
  const [projects, setProjects] = useState<Project[]>([])
  const [chapters, setChapters] = useState<RecycledChapter[]>([])
  const [tab, setTab] = useState<Tab>('projects')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [query, setQuery] = useState('')
  const [notice, setNotice] = useState('')
  const [selection, setSelection] = useState<Selection | null>(null)

  const loadRecycleBin = useCallback(() => {
    setLoading(true)
    setError('')
    Promise.all([api.getRecycledProjects(), api.getRecycledChapters()])
      .then(([projectList, chapterList]) => {
        setProjects(projectList)
        setChapters(chapterList)
      })
      .catch((reason) => setError(reason.message))
      .finally(() => setLoading(false))
  }, [])

  useEffect(loadRecycleBin, [loadRecycleBin])

  const filteredProjects = useMemo(() => {
    const keyword = query.trim().toLowerCase()
    return projects.filter((project) => `${project.projectname || ''} ${project.introduction || ''}`.toLowerCase().includes(keyword))
  }, [projects, query])

  const filteredChapters = useMemo(() => {
    const keyword = query.trim().toLowerCase()
    return chapters.filter((chapter) => `${chapterTitle(chapter)} ${chapter.projectname || ''}`.toLowerCase().includes(keyword))
  }, [chapters, query])

  function selectProjectAction(project: Project, action: ProjectAction) {
    setNotice('')
    setSelection({ kind: 'project', item: project, action })
  }

  function selectChapterAction(chapter: RecycledChapter, action: ChapterAction) {
    setNotice('')
    setSelection({ kind: 'chapter', item: chapter, action })
  }

  function handleProjectSuccess(project: Project) {
    setProjects((current) => current.filter((item) => item.id !== project.id))
    const action = selection?.kind === 'project' ? selection.action : 'restore'
    setChapters((current) => action === 'delete'
      ? current.filter((chapter) => chapter.project_id !== project.id)
      : current.map((chapter) => chapter.project_id === project.id ? { ...chapter, project_status: null } : chapter))
    setNotice(`《${project.projectname || '未命名作品'}》已${action === 'restore' ? '还原，可在作品列表中继续查看' : '彻底删除'}。`)
    setSelection(null)
  }

  function handleChapterSuccess(chapter: Chapter) {
    setChapters((current) => current.filter((item) => item.id !== chapter.id))
    const action = selection?.kind === 'chapter' ? selection.action : 'restore'
    setNotice(`《${chapter.chaptername || `第 ${chapter.chapter_number} 章`}》已${action === 'restore' ? '还原' : '彻底删除'}。`)
    setSelection(null)
  }

  const visibleCount = tab === 'projects' ? filteredProjects.length : filteredChapters.length

  function handleTabKey(event: KeyboardEvent<HTMLDivElement>) {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return
    event.preventDefault()
    const nextTab = event.key === 'Home' ? 'projects' : event.key === 'End' ? 'chapters' : tab === 'projects' ? 'chapters' : 'projects'
    setTab(nextTab)
    event.currentTarget.querySelector<HTMLButtonElement>(`#recycle-${nextTab}-tab`)?.focus()
  }

  return (
    <div className="page">
      <header className="page-header">
        <div><p className="eyebrow">作品管理</p><h1>回收站</h1><p>还原暂别的故事和章节，或彻底删除不再需要的内容。</p></div>
        <Link className="secondary-button" to="/projects"><ArrowLeft size={17} />返回作品</Link>
      </header>

      <div className="recycle-hint"><Trash2 size={18} aria-hidden="true" /><p>回收站中的内容会保留，直到你选择彻底删除。彻底删除后无法恢复。</p></div>
      {notice && <div className="form-message success page-notice" role="status">{notice}</div>}

      <div className="recycle-tabs" role="tablist" aria-label="回收站内容类型" onKeyDown={handleTabKey}>
        <button id="recycle-projects-tab" role="tab" aria-selected={tab === 'projects'} tabIndex={tab === 'projects' ? 0 : -1} aria-controls="recycle-content" className={tab === 'projects' ? 'active' : ''} onClick={() => setTab('projects')}>作品 <span>{projects.length}</span></button>
        <button id="recycle-chapters-tab" role="tab" aria-selected={tab === 'chapters'} tabIndex={tab === 'chapters' ? 0 : -1} aria-controls="recycle-content" className={tab === 'chapters' ? 'active' : ''} onClick={() => setTab('chapters')}>章节 <span>{chapters.length}</span></button>
      </div>

      <div className="toolbar">
        <label className="search-box"><Search size={17} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder={tab === 'projects' ? '搜索回收站中的作品' : '搜索章节名或所属作品'} aria-label="搜索回收站" /></label>
        <span className="result-count">共 {visibleCount} 项</span>
      </div>

      <div id="recycle-content" role="tabpanel" aria-labelledby={`recycle-${tab}-tab`}>
      {error ? <div className="empty-state"><p role="alert">{error}</p><button className="secondary-button" onClick={loadRecycleBin}>重新加载</button></div>
        : loading ? <div className="project-grid skeleton-grid" aria-label="正在加载回收站"><span /><span /><span /></div>
        : tab === 'projects' ? filteredProjects.length === 0 ? (
          <div className="empty-state"><Trash2 size={32} /><h3>{query.trim() ? '没有匹配的作品' : '没有已删除的作品'}</h3><p>{query.trim() ? '换一个关键词试试。' : '移入回收站的作品会显示在这里。'}</p><Link className="secondary-button" to="/projects">返回作品列表</Link></div>
        ) : (
          <div className="project-grid">
            {filteredProjects.map((project) => (
              <article className="project-card" key={project.id}>
                <div className="project-card-top"><span className="project-monogram">{(project.projectname || '未').slice(0, 1)}</span><span className="status-badge paused">回收站</span></div>
                <h2>{project.projectname || '未命名作品'}</h2>
                <p>{project.introduction || '尚未填写作品简介'}</p>
                <div className="project-stats"><span><FileText size={15} />{project.chapter_count} 章</span><span>{numberFormat.format(project.total_words)} 字</span></div>
                <div className="project-updated"><CalendarDays size={14} />移入于 {dateFormat.format(new Date(project.updated_at))}</div>
                <div className="project-card-actions">
                  <button className="secondary-button" type="button" onClick={() => selectProjectAction(project, 'restore')} aria-label={`还原${project.projectname || '未命名作品'}`}><RotateCcw size={15} />还原</button>
                  <button className="secondary-button danger-button" type="button" onClick={() => selectProjectAction(project, 'delete')} aria-label={`彻底删除${project.projectname || '未命名作品'}`}><Trash2 size={15} />彻底删除</button>
                </div>
              </article>
            ))}
          </div>
        ) : filteredChapters.length === 0 ? (
          <div className="empty-state"><FileText size={32} /><h3>{query.trim() ? '没有匹配的章节' : '没有已删除的章节'}</h3><p>{query.trim() ? '换一个章节名或作品名试试。' : '从作品中移入回收站的章节会显示在这里。'}</p></div>
        ) : (
          <div className="recycled-chapter-list">
            {filteredChapters.map((chapter) => (
              <article className="recycled-chapter-row" key={chapter.id}>
                <span className="chapter-number">{String(chapter.chapter_number).padStart(2, '0')}</span>
                <div className="recycled-chapter-copy"><h2>{chapterTitle(chapter)}</h2><p>所属作品：{chapter.projectname || '未命名作品'}</p>{chapter.project_status === '回收站' && <p className="error-copy">请先还原所属作品</p>}</div>
                <span className="project-updated"><CalendarDays size={14} />移入于 {dateFormat.format(new Date(chapter.updated_at))}</span>
                <div className="project-card-actions">
                  <button className="secondary-button" type="button" onClick={() => selectChapterAction(chapter, 'restore')} aria-label={`还原${chapterTitle(chapter)}`} disabled={chapter.project_status === '回收站'} title={chapter.project_status === '回收站' ? '请先还原所属作品' : undefined}><RotateCcw size={15} />还原</button>
                  <button className="secondary-button danger-button" type="button" onClick={() => selectChapterAction(chapter, 'delete')} aria-label={`彻底删除${chapterTitle(chapter)}`}><Trash2 size={15} />彻底删除</button>
                </div>
              </article>
            ))}
          </div>
        )}
      </div>

      <ProjectActionDialog project={selection?.kind === 'project' ? selection.item : null} action={selection?.kind === 'project' ? selection.action : 'restore'} onClose={() => setSelection(null)} onSuccess={handleProjectSuccess} />
      <ChapterActionDialog chapter={selection?.kind === 'chapter' ? selection.item : null} action={selection?.kind === 'chapter' ? selection.action : 'restore'} onClose={() => setSelection(null)} onSuccess={handleChapterSuccess} />
    </div>
  )
}
