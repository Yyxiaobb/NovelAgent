import { ArrowRight, BookOpenText, FileText, Plus, TrendingUp } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import type { Project } from '../types'

const numberFormat = new Intl.NumberFormat('zh-CN')
const dateFormat = new Intl.DateTimeFormat('zh-CN', { month: 'short', day: 'numeric' })

export function DashboardPage() {
  const { user } = useAuth()
  const navigate = useNavigate()
  const [projects, setProjects] = useState<Project[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const loadProjects = useCallback(() => {
    setLoading(true)
    setError('')
    api
      .getProjects()
      .then(setProjects)
      .catch(reason => setError(reason.message))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    loadProjects()
    window.addEventListener('projects:changed', loadProjects)
    return () => window.removeEventListener('projects:changed', loadProjects)
  }, [loadProjects])

  const totals = useMemo(
    () => ({
      words: projects.reduce((sum, project) => sum + project.total_words, 0),
      chapters: projects.reduce((sum, project) => sum + project.chapter_count, 0),
    }),
    [projects],
  )

  const recentProjects = [...projects].sort((a, b) => Date.parse(b.updated_at) - Date.parse(a.updated_at)).slice(0, 4)

  return (
    <div className="page">
      <header className="page-header dashboard-header">
        <div>
          <p className="eyebrow">创作概览</p>
          <h1>{user?.nickname || user?.username}，今天写点什么？</h1>
          <p>故事不必一次写完，但值得每天向前一点。</p>
        </div>
        <Link className="primary-button" to="/?create=1">
          <Plus size={17} />
          新建作品
        </Link>
      </header>

      <section className="metrics-grid" aria-label="作品统计">
        <article className="metric">
          <span className="metric-icon red">
            <BookOpenText size={20} />
          </span>
          <div>
            <small>作品总数</small>
            <strong>{loading ? '—' : projects.length}</strong>
          </div>
        </article>
        <article className="metric">
          <span className="metric-icon teal">
            <FileText size={20} />
          </span>
          <div>
            <small>累计章节</small>
            <strong>{loading ? '—' : numberFormat.format(totals.chapters)}</strong>
          </div>
        </article>
        <article className="metric">
          <span className="metric-icon gold">
            <TrendingUp size={20} />
          </span>
          <div>
            <small>累计字数</small>
            <strong>{loading ? '—' : numberFormat.format(totals.words)}</strong>
          </div>
        </article>
      </section>

      <section className="content-section">
        <div className="section-heading">
          <div>
            <h2>最近作品</h2>
            <p>按最后更新时间排列</p>
          </div>
          <Link className="text-link" to="/projects">
            查看全部 <ArrowRight size={15} />
          </Link>
        </div>
        {error ? (
          <div className="empty-state compact">
            <p>{error}</p>
            <button className="secondary-button" onClick={() => window.location.reload()}>
              重新加载
            </button>
          </div>
        ) : loading ? (
          <div className="project-list skeleton-list">
            <span />
            <span />
            <span />
          </div>
        ) : recentProjects.length === 0 ? (
          <div className="empty-state">
            <BookOpenText size={30} />
            <h3>还没有作品</h3>
            <p>创建第一部作品，让想法有一个清晰的起点。</p>
          </div>
        ) : (
          <div className="project-list">
            {recentProjects.map(project => (
              <article
                className="project-row project-row-clickable"
                key={project.id}
                role="link"
                tabIndex={0}
                aria-label={`查看${project.projectname || '未命名作品'}详情`}
                onClick={event => {
                  if ((event.target as HTMLElement).closest('a, button')) return
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
                <span className="book-spine" aria-hidden="true" />
                <div className="project-main">
                  <h3>
                    <Link className="project-card-link" to={`/projects/${project.id}`}>
                      {project.projectname || '未命名作品'}
                    </Link>
                  </h3>
                  <p>{project.introduction || '尚未填写作品简介'}</p>
                </div>
                <div className="project-meta">
                  <span>{project.chapter_count} 章</span>
                  <span>{numberFormat.format(project.total_words)} 字</span>
                </div>
                <time dateTime={project.updated_at}>{dateFormat.format(new Date(project.updated_at))}</time>
                <span
                  className={`status-badge ${project.status === '完结' ? 'done' : project.status === '断更' ? 'paused' : ''}`}
                >
                  {project.status}
                </span>
              </article>
            ))}
          </div>
        )}
      </section>
    </div>
  )
}
