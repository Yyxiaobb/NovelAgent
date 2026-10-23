import { BookOpenText, CalendarDays, ChevronDown, ChevronUp, FileText, Plus, Search, Trash2 } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import { ChapterActionDialog } from '../components/ChapterActionDialog'
import { ProjectActionDialog } from '../components/ProjectActionDialog'
import type { Chapter, Project } from '../types'

const numberFormat = new Intl.NumberFormat('zh-CN')
const dateFormat = new Intl.DateTimeFormat('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' })

function chapterTitle(chapter: Chapter) {
  return chapter.chaptername || `第 ${chapter.chapter_number} 章`
}

export function ProjectsPage() {
  const navigate = useNavigate()
  const [projects, setProjects] = useState<Project[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [query, setQuery] = useState('')
  const [recycleTarget, setRecycleTarget] = useState<Project | null>(null)
  const [chapterRecycleTarget, setChapterRecycleTarget] = useState<Chapter | null>(null)
  const [expandedProjectId, setExpandedProjectId] = useState<number | null>(null)
  const [chapterList, setChapterList] = useState<Chapter[]>([])
  const [loadingChapters, setLoadingChapters] = useState(false)
  const [chapterError, setChapterError] = useState('')
  const [chapterReloadKey, setChapterReloadKey] = useState(0)
  const [notice, setNotice] = useState('')
  const loadProjects = useCallback(() => {
    setLoading(true)
    setError('')
    api
      .getProjects()
      .then(setProjects)
      .catch(reason => setError(reason.message))
      .finally(() => setLoading(false))
  }, [])

  useEffect(loadProjects, [loadProjects])

  useEffect(() => {
    window.addEventListener('projects:changed', loadProjects)
    return () => window.removeEventListener('projects:changed', loadProjects)
  }, [loadProjects])

  useEffect(() => {
    if (expandedProjectId === null) return
    let cancelled = false
    setLoadingChapters(true)
    setChapterError('')
    api
      .getProjectChapters(expandedProjectId)
      .then(chapters => {
        if (!cancelled) setChapterList(chapters)
      })
      .catch(reason => {
        if (!cancelled) setChapterError(reason instanceof Error ? reason.message : '章节加载失败，请稍后重试')
      })
      .finally(() => {
        if (!cancelled) setLoadingChapters(false)
      })
    return () => {
      cancelled = true
    }
  }, [expandedProjectId, chapterReloadKey])

  function toggleChapters(project: Project) {
    setChapterList([])
    setChapterError('')
    if (expandedProjectId === project.id) {
      setExpandedProjectId(null)
      return
    }

    setLoadingChapters(true)
    setExpandedProjectId(project.id)
  }

  const filteredProjects = useMemo(() => {
    const keyword = query.trim().toLowerCase()
    if (!keyword) return projects
    return projects.filter(project =>
      `${project.projectname || ''} ${project.introduction || ''}`.toLowerCase().includes(keyword),
    )
  }, [projects, query])

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <p className="eyebrow">作品管理</p>
          <h1>我的作品</h1>
          <p>集中查看小说项目与创作进度。</p>
        </div>
        <div className="header-actions">
          <button className="primary-button" onClick={() => navigate('/?create=1')}>
            <Plus size={17} />
            新建作品
          </button>
        </div>
      </header>

      {notice && (
        <div className="form-message success page-notice" role="status">
          {notice}{' '}
          <Link className="text-link" to="/recycle-bin">
            查看回收站
          </Link>
        </div>
      )}

      <div className="toolbar">
        <label className="search-box">
          <Search size={17} />
          <input
            value={query}
            onChange={event => setQuery(event.target.value)}
            placeholder="搜索作品名称或简介"
            aria-label="搜索作品"
          />
        </label>
        <span className="result-count">共 {filteredProjects.length} 部作品</span>
      </div>

      {error ? (
        <div className="form-message error" role="alert">
          <p>{error}</p>
        </div>
      ) : loading ? (
        <div className="project-grid skeleton-grid">
          <span />
          <span />
          <span />
        </div>
      ) : filteredProjects.length === 0 ? (
        <div className="empty-state">
          <BookOpenText size={32} />
          <h3>{query ? '没有匹配的作品' : '当前暂无作品，快去创建你的第一个作品吧！'}</h3>
          {query && <p>换一个关键词试试。</p>}
        </div>
      ) : (
        <div className="project-grid">
          {filteredProjects.map(project => (
            <article
              className="project-card project-card-clickable"
              key={project.id}
              role="link"
              tabIndex={0}
              aria-label={`查看${project.projectname || '未命名作品'}详情`}
              onClick={event => {
                if ((event.target as HTMLElement).closest('button, a')) return
                navigate(`/projects/${project.id}`)
              }}
              onKeyDown={event => {
                if (event.target !== event.currentTarget) return
                if (event.key === 'Enter' || event.key === ' ') {
                  event.preventDefault()
                  navigate(`/projects/${project.id}`)
                }
              }}
            >
              <div className="project-card-top">
                <span className="project-monogram">{(project.projectname || '未').slice(0, 1)}</span>
                <span
                  className={`status-badge ${project.status === '完结' ? 'done' : project.status === '断更' ? 'paused' : ''}`}
                >
                  {project.status || '连载中'}
                </span>
              </div>
              <h2>
                <Link className="project-card-link" to={`/projects/${project.id}`}>
                  {project.projectname || '未命名作品'}
                </Link>
              </h2>
              <p>{project.introduction || '尚未填写作品简介'}</p>
              <div className="project-stats">
                <span>
                  <FileText size={15} />
                  {project.chapter_count} 章
                </span>
                <span>{numberFormat.format(project.total_words)} 字</span>
              </div>
              <div className="project-updated">
                <CalendarDays size={14} />
                更新于 {dateFormat.format(new Date(project.updated_at))}
              </div>
              <Link className="chapter-toggle outline-toggle" to={`/projects/${project.id}/outline`}>
                <BookOpenText size={15} />
                管理大纲
              </Link>
              <button
                className="chapter-toggle"
                type="button"
                aria-expanded={expandedProjectId === project.id}
                aria-controls={`project-${project.id}-chapters`}
                onClick={() => void toggleChapters(project)}
              >
                <FileText size={15} />
                管理章节（{project.chapter_count}）
                {expandedProjectId === project.id ? <ChevronUp size={15} /> : <ChevronDown size={15} />}
              </button>
              {expandedProjectId === project.id && (
                <div className="chapter-panel" id={`project-${project.id}-chapters`}>
                  {loadingChapters ? (
                    <p className="chapter-placeholder">正在加载章节…</p>
                  ) : chapterError ? (
                    <div className="chapter-placeholder error-copy" role="alert">
                      {chapterError}
                      <button className="text-link" type="button" onClick={() => setChapterReloadKey(key => key + 1)}>
                        重新加载
                      </button>
                    </div>
                  ) : chapterList.length === 0 ? (
                    <p className="chapter-placeholder">这部作品还没有可管理的章节。</p>
                  ) : (
                    chapterList.map(chapter => (
                      <div className="chapter-row" key={chapter.id}>
                        <span className="chapter-number">{String(chapter.chapter_number).padStart(2, '0')}</span>
                        <span className="chapter-row-name">{chapterTitle(chapter)}</span>
                        <button
                          className="icon-button chapter-delete-button"
                          type="button"
                          aria-label={`将${chapterTitle(chapter)}移入回收站`}
                          onClick={() => setChapterRecycleTarget(chapter)}
                        >
                          <Trash2 size={15} />
                        </button>
                      </div>
                    ))
                  )}
                </div>
              )}
              <div className="project-card-actions">
                <button
                  className="secondary-button danger-button"
                  type="button"
                  onClick={() => {
                    setNotice('')
                    setRecycleTarget(project)
                  }}
                  aria-label={`将${project.projectname || '未命名作品'}移入回收站`}
                >
                  <Trash2 size={15} />
                  移入回收站
                </button>
              </div>
            </article>
          ))}
        </div>
      )}

      <ProjectActionDialog
        project={recycleTarget}
        action="recycle"
        onClose={() => setRecycleTarget(null)}
        onSuccess={project => {
          setProjects(current => current.filter(item => item.id !== project.id))
          if (expandedProjectId === project.id) setExpandedProjectId(null)
          setRecycleTarget(null)
          setNotice(`《${project.projectname || '未命名作品'}》已移入回收站。`)
        }}
      />
      <ChapterActionDialog
        chapter={chapterRecycleTarget}
        action="recycle"
        onClose={() => setChapterRecycleTarget(null)}
        onSuccess={chapter => {
          setChapterList(current => current.filter(item => item.id !== chapter.id))
          setProjects(current =>
            current.map(project =>
              project.id === chapter.project_id
                ? { ...project, chapter_count: Math.max(0, project.chapter_count - 1) }
                : project,
            ),
          )
          setChapterRecycleTarget(null)
          setNotice(`《${chapterTitle(chapter)}》已移入回收站。`)
        }}
      />
    </div>
  )
}
