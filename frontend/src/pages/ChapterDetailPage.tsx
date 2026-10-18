import {
  ArrowLeft,
  BookOpenText,
  Edit3,
  History,
  PanelLeftClose,
  PanelLeftOpen,
  RotateCcw,
  Save,
  Sparkles,
  X,
} from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'
import { api } from '../api/client'
import type { Chapter, ChapterMemory, ChapterPlan, ChapterVersion, GenerationJob } from '../types'

export function ChapterDetailPage() {
  const { projectId, chapterId, feature } = useParams()
  const location = useLocation()
  const navigate = useNavigate()
  const { state: routeState } = location
  const [chapter, setChapter] = useState<Chapter | null>(null)
  const [draft, setDraft] = useState({ chapter_number: '', chaptername: '', content: '' })
  const [planDraft, setPlanDraft] = useState<ChapterPlan>({
    objective: '',
    conflict: '',
    key_events: '',
    ending_hook: '',
    expected_words: 3000,
  })
  const [summaryDraft, setSummaryDraft] = useState('')
  const [memoryDraft, setMemoryDraft] = useState<ChapterMemory | null>(null)
  const [editing, setEditing] = useState(false)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [generationProgress, setGenerationProgress] = useState(0)
  const [generationIdea, setGenerationIdea] = useState('')
  const [generationDialogOpen, setGenerationDialogOpen] = useState(false)
  const [generationError, setGenerationError] = useState('')
  const [planGenerationOpen, setPlanGenerationOpen] = useState(false)
  const [planGenerationIdea, setPlanGenerationIdea] = useState('')
  const [planGenerating, setPlanGenerating] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [generationJobs, setGenerationJobs] = useState<GenerationJob[]>([])
  const [historyLoading, setHistoryLoading] = useState(false)
  const [historyOpen, setHistoryOpen] = useState(false)
  const [versions, setVersions] = useState<ChapterVersion[]>([])
  const [versionsOpen, setVersionsOpen] = useState(false)
  const [versionsLoading, setVersionsLoading] = useState(false)
  const [restoringVersion, setRestoringVersion] = useState<number | null>(null)
  const [retryingJob, setRetryingJob] = useState<string | null>(null)
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)

  const loadChapter = useCallback(async () => {
    const project = Number(projectId)
    const id = Number(chapterId)
    if (!Number.isInteger(project) || project <= 0 || !Number.isInteger(id) || id <= 0) {
      throw new Error('章节编号无效')
    }
    const value = await api.getChapter(project, id)
    setChapter(value)
    setDraft({
      chapter_number: String(value.chapter_number),
      chaptername: value.chaptername || '',
      content: value.content || '',
    })
    setPlanDraft(value.plan || { objective: '', conflict: '', key_events: '', ending_hook: '', expected_words: 3000 })
    setSummaryDraft(value.summary || '')
    setMemoryDraft(value.memory || null)
  }, [chapterId, projectId])

  useEffect(() => {
    setLoading(true)
    setError('')
    void loadChapter()
      .catch(reason => setError(reason instanceof Error ? reason.message : '章节加载失败，请稍后重试'))
      .finally(() => setLoading(false))
  }, [loadChapter])

  useEffect(() => {
    if (feature === 'edit' || feature === 'plan' || feature === 'generate') setEditing(true)
    const restoreState = routeState as { generatedContent?: string; plan?: ChapterPlan | null } | null
    if (feature === 'edit' && restoreState?.generatedContent) {
      setEditing(true)
      setDraft(current => ({ ...current, content: restoreState.generatedContent || '' }))
      if (restoreState.plan) setPlanDraft(restoreState.plan)
    }
    if (feature === 'plan' && !loading) setPlanGenerationOpen(true)
    if (feature === 'generate' && !loading) setGenerationDialogOpen(true)
    if (feature === 'history') setHistoryOpen(true)
    if (feature === 'versions') setVersionsOpen(true)
  }, [feature, loading, routeState])

  const loadGenerationJobs = useCallback(async () => {
    if (!chapter) return
    const listJobs = (
      api as typeof api & {
        listChapterContentJobs?: (projectId?: number, chapterId?: number) => Promise<GenerationJob[]>
      }
    ).listChapterContentJobs
    if (typeof listJobs !== 'function') return
    setHistoryLoading(true)
    try {
      setGenerationJobs(await listJobs(chapter.project_id, chapter.id))
    } catch {
      // History is supplementary; an unavailable history endpoint must not
      // block editing an otherwise usable chapter.
    } finally {
      setHistoryLoading(false)
    }
  }, [chapter])

  useEffect(() => {
    if (!historyOpen) return
    let disposed = false
    let timer: number | undefined
    const refresh = async () => {
      await loadGenerationJobs()
      if (!disposed) timer = window.setTimeout(() => void refresh(), 2000)
    }
    void refresh()
    return () => {
      disposed = true
      if (timer !== undefined) window.clearTimeout(timer)
    }
  }, [historyOpen, loadGenerationJobs])

  async function cancelGenerationJob(jobId: string) {
    const cancelJob = (api as typeof api & { cancelChapterContentJob?: (id: string) => Promise<unknown> })
      .cancelChapterContentJob
    if (typeof cancelJob !== 'function') return
    try {
      await cancelJob(jobId)
      await loadGenerationJobs()
      setNotice('生成任务已取消')
    } catch (reason) {
      setNotice(reason instanceof Error ? reason.message : '取消生成任务失败，请稍后重试')
    }
  }

  async function retryGenerationJob(jobId: string) {
    const retryJob = (api as typeof api & { retryChapterContentJob?: (id: string) => Promise<unknown> })
      .retryChapterContentJob
    if (typeof retryJob !== 'function') return
    setRetryingJob(jobId)
    try {
      await retryJob(jobId)
      await loadGenerationJobs()
      setNotice('已重新创建生成任务，页面会自动更新进度')
    } catch (reason) {
      setNotice(reason instanceof Error ? reason.message : '重新生成失败，请稍后重试')
    } finally {
      setRetryingJob(null)
    }
  }

  const loadVersions = useCallback(async () => {
    if (!chapter) return
    const getVersions = (
      api as typeof api & { getChapterVersions?: (projectId: number, chapterId: number) => Promise<ChapterVersion[]> }
    ).getChapterVersions
    if (typeof getVersions !== 'function') return
    setVersionsLoading(true)
    try {
      setVersions(await getVersions(chapter.project_id, chapter.id))
    } catch {
      setNotice('版本历史暂时无法加载')
    } finally {
      setVersionsLoading(false)
    }
  }, [chapter])

  useEffect(() => {
    if (versionsOpen) void loadVersions()
  }, [versionsOpen, loadVersions])

  async function restoreVersion(version: ChapterVersion) {
    const restore = (
      api as typeof api & {
        restoreChapterVersion?: (projectId: number, chapterId: number, versionId: number) => Promise<Chapter>
      }
    ).restoreChapterVersion
    if (typeof restore !== 'function' || !chapter) return
    if (!window.confirm(`确定恢复到第 ${version.version_number} 个版本吗？当前内容会自动保存为新版本。`)) return
    setRestoringVersion(version.id)
    try {
      const restored = await restore(chapter.project_id, chapter.id, version.id)
      setChapter(restored)
      setDraft({
        chapter_number: String(restored.chapter_number),
        chaptername: restored.chaptername || '',
        content: restored.content || '',
      })
      setPlanDraft(
        restored.plan || { objective: '', conflict: '', key_events: '', ending_hook: '', expected_words: 3000 },
      )
      setSummaryDraft(restored.summary || '')
      setMemoryDraft(restored.memory || null)
      setEditing(false)
      setNotice(`已恢复第 ${version.version_number} 个版本`)
      await loadVersions()
    } catch (reason) {
      setNotice(reason instanceof Error ? reason.message : '恢复版本失败，请稍后重试')
    } finally {
      setRestoringVersion(null)
    }
  }

  function beginEditing() {
    if (!chapter) return
    setDraft({
      chapter_number: String(chapter.chapter_number),
      chaptername: chapter.chaptername || '',
      content: chapter.content || '',
    })
    setPlanDraft(chapter.plan || { objective: '', conflict: '', key_events: '', ending_hook: '', expected_words: 3000 })
    setSummaryDraft(chapter.summary || '')
    setMemoryDraft(chapter.memory || null)
    setNotice('')
    setEditing(true)
  }

  function cancelEditing() {
    if (chapter) {
      setDraft({
        chapter_number: String(chapter.chapter_number),
        chaptername: chapter.chaptername || '',
        content: chapter.content || '',
      })
      setPlanDraft(
        chapter.plan || { objective: '', conflict: '', key_events: '', ending_hook: '', expected_words: 3000 },
      )
      setSummaryDraft(chapter.summary || '')
      setMemoryDraft(chapter.memory || null)
    }
    setEditing(false)
    setNotice('')
  }

  async function saveChapter() {
    if (!chapter) return
    const number = Number(draft.chapter_number)
    if (!Number.isInteger(number) || number <= 0 || !draft.chaptername.trim()) {
      setNotice('章节编号和章节名称不能为空')
      return
    }
    setSaving(true)
    setNotice('')
    try {
      const plan =
        planDraft.objective.trim() ||
        planDraft.conflict.trim() ||
        planDraft.key_events.trim() ||
        planDraft.ending_hook.trim()
          ? planDraft
          : undefined
      const contentChanged = draft.content !== (chapter.content || '')
      const summaryChanged = summaryDraft !== (chapter.summary || '')
      const memoryChanged = JSON.stringify(memoryDraft) !== JSON.stringify(chapter.memory || null)
      const shouldRefreshMemory =
        Boolean(draft.content.trim()) && (contentChanged || !chapter.summary) && !summaryChanged && !memoryChanged
      const updated = await api.updateChapter(chapter.project_id, chapter.id, {
        chapter_number: number,
        chaptername: draft.chaptername.trim(),
        content: draft.content,
        ...(plan ? { plan } : {}),
        ...(summaryChanged ? { summary: summaryDraft || null } : {}),
        ...(memoryChanged ? { memory: memoryDraft } : {}),
      })
      setChapter(updated)
      setDraft({
        chapter_number: String(updated.chapter_number),
        chaptername: updated.chaptername || '',
        content: updated.content || '',
      })
      setSummaryDraft(updated.summary || summaryDraft)
      setMemoryDraft(updated.memory || memoryDraft)
      setEditing(false)
      setNotice('章节修改已保存')
      if (shouldRefreshMemory && api.generateChapterMemory) {
        try {
          const memory = await api.generateChapterMemory(chapter.project_id, chapter.id)
          setChapter(current => (current ? { ...current, summary: memory.summary, memory: memory.memory } : current))
          setSummaryDraft(memory.summary)
          setMemoryDraft(memory.memory)
          setNotice('章节已保存，摘要和前文记忆已更新')
        } catch {
          setNotice('章节已保存，但摘要整理失败，可稍后重试')
        }
      }
    } catch (reason) {
      setNotice(reason instanceof Error ? reason.message : '章节保存失败，请稍后重试')
    } finally {
      setSaving(false)
    }
  }

  async function generateChapterPlan() {
    if (!chapter) return
    const words = Number(planDraft.expected_words)
    if (!Number.isInteger(words) || words <= 0 || words > 100000) {
      setGenerationError('请输入 1 到 100000 之间的本章目标字数')
      return
    }
    setPlanGenerating(true)
    setGenerationError('')
    try {
      const result = await api.generateChapterPlan(chapter.project_id, chapter.id, words, planGenerationIdea)
      setPlanDraft(result.plan)
      setPlanGenerationOpen(false)
      setNotice('章节规划已生成，请检查后保存章节')
    } catch (reason) {
      setGenerationError(reason instanceof Error ? reason.message : '章节规划生成失败，请稍后重试')
    } finally {
      setPlanGenerating(false)
    }
  }

  async function generateChapterContent() {
    if (!chapter) return
    const words = Number(planDraft.expected_words)
    if (!Number.isInteger(words) || words <= 0 || words > 100000) {
      setGenerationError('请输入 1 到 100000 之间的本章目标字数')
      return
    }
    if (
      !planDraft.objective.trim() ||
      !planDraft.conflict.trim() ||
      !planDraft.key_events.trim() ||
      !planDraft.ending_hook.trim()
    ) {
      setGenerationError('请先填写或生成完整的章节规划')
      return
    }
    setGenerating(true)
    setGenerationProgress(0)
    setGenerationError('')
    setDraft(current => ({ ...current, content: '' }))
    try {
      const plan = { ...planDraft, expected_words: words }
      const streamGenerator = (
        api as typeof api & { generateChapterContentStream?: typeof api.generateChapterContentStream }
      ).generateChapterContentStream
      const result =
        typeof streamGenerator === 'function'
          ? await streamGenerator(chapter.project_id, chapter.id, plan, generationIdea, chunk => {
              setGenerationProgress(current =>
                Math.min(99, current + Math.max(1, Math.round((chunk.length / Math.max(1, words)) * 100))),
              )
              setDraft(current => ({ ...current, content: current.content + chunk }))
            })
          : await api.generateChapterContent(chapter.project_id, chapter.id, plan, generationIdea)
      setDraft(current => ({ ...current, content: result.content }))
      setGenerationDialogOpen(false)
      setNotice('章节正文已生成，请检查后点击“保存修改”入库')
    } catch (reason) {
      setGenerationError(reason instanceof Error ? reason.message : '章节生成失败，请稍后重试')
    } finally {
      setGenerating(false)
      setGenerationProgress(100)
    }
  }

  if (loading)
    return (
      <div className="page">
        <div className="project-detail-skeleton" aria-label="正在加载章节详情">
          <span />
          <span />
          <span />
        </div>
      </div>
    )
  if (error || !chapter)
    return (
      <div className="page">
        <div className="empty-state">
          <BookOpenText size={32} />
          <h3>{error || '章节不存在'}</h3>
          <p>章节可能已被移入回收站，或暂时无法访问。</p>
          <Link className="secondary-button" to={`/projects/${projectId}`}>
            <ArrowLeft size={16} />
            返回作品详情
          </Link>
        </div>
      </div>
    )

  if (feature === 'history' || feature === 'versions') {
    const isHistory = feature === 'history'
    return (
      <div className="page detail-page">
        <div className={sidebarCollapsed ? 'detail-layout detail-layout-collapsed' : 'detail-layout'}>
          <aside className={sidebarCollapsed ? 'detail-sidebar collapsed' : 'detail-sidebar'} aria-label="章节功能侧栏">
            <Link className="text-link detail-sidebar-back" to={`/projects/${projectId}`}>
              <ArrowLeft size={16} />
              返回作品详情
            </Link>
            <button
              className="icon-button detail-sidebar-collapse"
              type="button"
              onClick={() => setSidebarCollapsed(current => !current)}
              aria-label={sidebarCollapsed ? '展开章节功能侧栏' : '收起章节功能侧栏'}
            >
              {sidebarCollapsed ? <PanelLeftOpen size={16} /> : <PanelLeftClose size={16} />}
            </button>
            <p className="detail-sidebar-eyebrow">章节工具</p>
            <Link
              className="detail-sidebar-link detail-sidebar-detail-link"
              to={`/projects/${projectId}/chapters/${chapterId}`}
            >
              <BookOpenText size={15} />
              章节详情
            </Link>
            <Link className="detail-sidebar-link" to={`/projects/${projectId}/chapters/${chapterId}/history`}>
              <History size={15} />
              生成历史
            </Link>
            <Link className="detail-sidebar-link" to={`/projects/${projectId}/chapters/${chapterId}/versions`}>
              <RotateCcw size={15} />
              章节版本
            </Link>
          </aside>
          <div className="detail-main">
            {notice && (
              <div className="form-message success page-notice" role="status">
                {notice}
              </div>
            )}
            <section className="content-section detail-subpage-panel">
              <p className="eyebrow">{isHistory ? '创作记录' : '版本管理'}</p>
              <h1>{isHistory ? '正文生成历史' : '章节版本'}</h1>
              <p className="outline-help">
                第 {chapter.chapter_number} 章 · {chapter.chaptername || '未命名章节'}
              </p>
              {isHistory ? (
                <section className="generation-history-panel">
                  {historyLoading && <p className="chapter-placeholder">正在加载生成历史…</p>}
                  {!historyLoading && generationJobs.length === 0 && (
                    <p className="chapter-placeholder">暂无长篇正文生成记录。</p>
                  )}
                  {!historyLoading &&
                    generationJobs.map(job => (
                      <article className="generation-history-item" key={job.job_id}>
                        <div className="generation-history-copy">
                          <strong>
                            {job.status === 'completed'
                              ? '生成完成'
                              : job.status === 'failed'
                                ? '生成失败'
                                : job.status === 'cancelled'
                                  ? '已取消'
                                  : `生成中 ${job.progress}%`}
                          </strong>
                          <small>
                            {new Date(job.created_at).toLocaleString()} ·{' '}
                            {job.expected_words ? `目标 ${job.expected_words} 字` : '章节正文'}
                          </small>
                          {job.error && <p className="error-copy">{job.error}</p>}
                        </div>
                        <div className="generation-history-actions">
                          {job.content && (
                            <button
                              className="secondary-button"
                              type="button"
                              onClick={() =>
                                navigate(`/projects/${projectId}/chapters/${chapterId}/edit`, {
                                  state: { generatedContent: job.content, plan: job.plan },
                                })
                              }
                            >
                              用作章节草稿
                            </button>
                          )}
                          {(job.status === 'queued' || job.status === 'running') && (
                            <button
                              className="secondary-button"
                              type="button"
                              onClick={() => void cancelGenerationJob(job.job_id)}
                            >
                              取消任务
                            </button>
                          )}
                          {(job.status === 'failed' || job.status === 'cancelled') && (
                            <button
                              className="secondary-button"
                              type="button"
                              onClick={() => void retryGenerationJob(job.job_id)}
                              disabled={retryingJob !== null}
                            >
                              {retryingJob === job.job_id ? '正在重新生成…' : '重新生成'}
                            </button>
                          )}
                        </div>
                      </article>
                    ))}
                </section>
              ) : (
                <section className="generation-history-panel chapter-version-panel">
                  {versionsLoading && <p className="chapter-placeholder">正在加载版本历史…</p>}
                  {!versionsLoading && versions.length === 0 && (
                    <p className="chapter-placeholder">保存章节后会在这里留下版本快照。</p>
                  )}
                  {!versionsLoading &&
                    versions.map(version => (
                      <article className="generation-history-item" key={version.id}>
                        <div className="generation-history-copy">
                          <strong>版本 {version.version_number}</strong>
                          <small>
                            {new Date(version.created_at).toLocaleString()} ·{' '}
                            {version.source === 'before_restore' ? '恢复前自动保存' : '保存前自动保存'}
                          </small>
                          <p>
                            {version.chaptername || `第 ${version.chapter_number} 章`} ·{' '}
                            {version.content ? `${version.content.length} 字` : '暂无正文'}
                          </p>
                        </div>
                        <div className="generation-history-actions">
                          <button
                            className="secondary-button"
                            type="button"
                            onClick={() => void restoreVersion(version)}
                            disabled={restoringVersion !== null}
                          >
                            {restoringVersion === version.id ? '正在恢复…' : '恢复此版本'}
                          </button>
                        </div>
                      </article>
                    ))}
                </section>
              )}
            </section>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="page detail-page">
      <div className={sidebarCollapsed ? 'detail-layout detail-layout-collapsed' : 'detail-layout'}>
        <aside className={sidebarCollapsed ? 'detail-sidebar collapsed' : 'detail-sidebar'} aria-label="章节功能侧栏">
          <Link className="text-link detail-sidebar-back" to={`/projects/${projectId}`}>
            <ArrowLeft size={16} />
            返回作品详情
          </Link>
          <button
            className="icon-button detail-sidebar-collapse"
            type="button"
            onClick={() => setSidebarCollapsed(current => !current)}
            aria-label={sidebarCollapsed ? '展开章节功能侧栏' : '收起章节功能侧栏'}
            title={sidebarCollapsed ? '展开章节功能侧栏' : '收起章节功能侧栏'}
          >
            {sidebarCollapsed ? <PanelLeftOpen size={16} /> : <PanelLeftClose size={16} />}
          </button>
          <p className="detail-sidebar-eyebrow">章节工具</p>
          <Link
            className="detail-sidebar-link detail-sidebar-detail-link"
            to={`/projects/${projectId}/chapters/${chapterId}`}
          >
            <BookOpenText size={15} />
            章节详情
          </Link>
          <Link className="detail-sidebar-link" to={`/projects/${projectId}/chapters/${chapterId}/history`}>
            <History size={15} />
            生成历史
          </Link>
          <Link className="detail-sidebar-link" to={`/projects/${projectId}/chapters/${chapterId}/versions`}>
            <RotateCcw size={15} />
            章节版本
          </Link>
        </aside>
        <div className="detail-main">
          {notice && (
            <div className="form-message success page-notice" role="status">
              {notice}
            </div>
          )}
          <div className="detail-page-toolbar">
            {editing ? (
              <>
                <button
                  className="secondary-button"
                  type="button"
                  onClick={cancelEditing}
                  disabled={saving || generating}
                >
                  <X size={15} />
                  取消编辑
                </button>
                <button
                  className="primary-button"
                  type="button"
                  onClick={() => void saveChapter()}
                  disabled={saving || generating}
                >
                  <Save size={15} />
                  {saving ? '正在保存…' : '保存修改'}
                </button>
              </>
            ) : (
              <button className="primary-button" type="button" onClick={beginEditing}>
                <Edit3 size={15} />
                编辑章节
              </button>
            )}
          </div>
          <section className="content-section chapter-detail-panel">
            <div className="chapter-detail-heading">
              <p className="eyebrow">章节详情</p>
              {editing ? (
                <div className="chapter-detail-fields">
                  <label className="detail-edit-field">
                    <span>章节编号</span>
                    <input
                      type="number"
                      min="1"
                      value={draft.chapter_number}
                      onChange={event => setDraft(current => ({ ...current, chapter_number: event.target.value }))}
                      aria-label="章节编号"
                    />
                  </label>
                  <label className="detail-edit-field">
                    <span>章节名称</span>
                    <input
                      value={draft.chaptername}
                      onChange={event => setDraft(current => ({ ...current, chaptername: event.target.value }))}
                      maxLength={50}
                      aria-label="章节名称"
                    />
                  </label>
                </div>
              ) : (
                <>
                  <span className="chapter-detail-number">第 {chapter.chapter_number} 章</span>
                  <h1>{chapter.chaptername || `第 ${chapter.chapter_number} 章`}</h1>
                </>
              )}
            </div>
            <section className="chapter-plan-panel">
              <div className="editor-field-heading">
                <span>章节规划</span>
              </div>
              {editing ? (
                <div className="chapter-plan-fields">
                  <label className="detail-edit-field">
                    <span>本章目标</span>
                    <textarea
                      value={planDraft.objective}
                      onChange={event => setPlanDraft(current => ({ ...current, objective: event.target.value }))}
                      rows={3}
                      aria-label="本章目标"
                    />
                  </label>
                  <label className="detail-edit-field">
                    <span>核心冲突</span>
                    <textarea
                      value={planDraft.conflict}
                      onChange={event => setPlanDraft(current => ({ ...current, conflict: event.target.value }))}
                      rows={3}
                      aria-label="核心冲突"
                    />
                  </label>
                  <label className="detail-edit-field">
                    <span>关键情节</span>
                    <textarea
                      value={planDraft.key_events}
                      onChange={event => setPlanDraft(current => ({ ...current, key_events: event.target.value }))}
                      rows={5}
                      aria-label="关键情节"
                    />
                  </label>
                  <label className="detail-edit-field">
                    <span>结尾钩子</span>
                    <textarea
                      value={planDraft.ending_hook}
                      onChange={event => setPlanDraft(current => ({ ...current, ending_hook: event.target.value }))}
                      rows={3}
                      aria-label="结尾钩子"
                    />
                  </label>
                  <label className="detail-edit-field plan-words-field">
                    <span>本章目标字数</span>
                    <input
                      type="number"
                      min="1"
                      max="100000"
                      value={planDraft.expected_words}
                      onChange={event =>
                        setPlanDraft(current => ({ ...current, expected_words: Number(event.target.value) }))
                      }
                      aria-label="本章规划目标字数"
                    />
                  </label>
                </div>
              ) : chapter.plan ? (
                <div className="chapter-plan-summary">
                  <p>
                    <strong>目标：</strong>
                    {chapter.plan.objective}
                  </p>
                  <p>
                    <strong>冲突：</strong>
                    {chapter.plan.conflict}
                  </p>
                  <p>
                    <strong>关键情节：</strong>
                    {chapter.plan.key_events}
                  </p>
                  <p>
                    <strong>结尾钩子：</strong>
                    {chapter.plan.ending_hook}
                  </p>
                </div>
              ) : (
                <p className="chapter-plan-empty">尚未制定章节规划。</p>
              )}
            </section>
            <section className="chapter-memory-panel">
              <div className="editor-field-heading">
                <span>章节摘要与前文记忆</span>
                {memoryDraft && !editing && <span className="memory-updated-label">已整理</span>}
              </div>
              {editing ? (
                <label className="detail-edit-field">
                  <span>章节摘要</span>
                  <textarea
                    value={summaryDraft}
                    onChange={event => setSummaryDraft(event.target.value)}
                    rows={4}
                    maxLength={20000}
                    aria-label="章节摘要"
                    placeholder="保存正文后会自动整理，也可以手动修改。"
                  />
                </label>
              ) : (
                <p className="chapter-summary-text">{chapter.summary || '保存章节正文后会自动整理摘要。'}</p>
              )}
              {memoryDraft && (
                <div className="chapter-memory-grid">
                  <p>
                    <strong>人物状态：</strong>
                    {memoryDraft.character_state}
                  </p>
                  <p>
                    <strong>设定变化：</strong>
                    {memoryDraft.setting_changes}
                  </p>
                  <p>
                    <strong>未解决线索：</strong>
                    {memoryDraft.unresolved_threads}
                  </p>
                  <p>
                    <strong>时间线：</strong>
                    {memoryDraft.timeline}
                  </p>
                </div>
              )}
            </section>
            <div className="chapter-content-field">
              <div className="editor-field-heading">
                <span>章节内容</span>
                {editing && (
                  <button
                    className="secondary-button"
                    type="button"
                    onClick={() => {
                      setGenerationIdea('')
                      setGenerationError('')
                      setGenerationDialogOpen(true)
                    }}
                    disabled={generating || saving}
                  >
                    <Sparkles size={15} />
                    按规划生成正文
                  </button>
                )}
              </div>
              {editing ? (
                <textarea
                  value={draft.content}
                  onChange={event => setDraft(current => ({ ...current, content: event.target.value }))}
                  rows={20}
                  aria-label="章节内容"
                  placeholder="在这里写下章节内容…"
                />
              ) : (
                <div className="chapter-content-view">{chapter.content || '尚未填写章节内容'}</div>
              )}
            </div>
          </section>
        </div>
      </div>
      {planGenerationOpen && (
        <div className="modal-backdrop" role="presentation">
          <section
            className="modal generation-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="chapter-plan-generation-title"
          >
            <div className="modal-header">
              <h2 id="chapter-plan-generation-title">智能生成章节规划</h2>
              <button
                className="icon-button"
                type="button"
                onClick={() => setPlanGenerationOpen(false)}
                aria-label="关闭章节规划生成弹窗"
                disabled={planGenerating}
              >
                <X size={18} />
              </button>
            </div>
            <div className="modal-body generation-modal-body">
              <label className="detail-edit-field">
                <span>本章期望字数</span>
                <input
                  type="number"
                  min="1"
                  max="100000"
                  value={planDraft.expected_words}
                  onChange={event =>
                    setPlanDraft(current => ({ ...current, expected_words: Number(event.target.value) }))
                  }
                  aria-label="本章规划目标字数"
                />
              </label>
              <label className="detail-edit-field">
                <span>你的想法（选填）</span>
                <textarea
                  value={planGenerationIdea}
                  onChange={event => setPlanGenerationIdea(event.target.value)}
                  rows={5}
                  maxLength={5000}
                  aria-label="章节规划想法"
                  placeholder="例如：本章让主角第一次进入遗迹，并在结尾发现敌人留下的信号。"
                />
              </label>
              {generationError && (
                <p className="form-message error" role="alert">
                  {generationError}
                </p>
              )}
              <div className="modal-actions">
                <button
                  className="secondary-button"
                  type="button"
                  onClick={() => setPlanGenerationOpen(false)}
                  disabled={planGenerating}
                >
                  取消
                </button>
                <button
                  className="primary-button"
                  type="button"
                  onClick={() => void generateChapterPlan()}
                  disabled={planGenerating}
                >
                  <Sparkles size={15} />
                  {planGenerating ? '正在生成…' : '生成规划'}
                </button>
              </div>
            </div>
          </section>
        </div>
      )}
      {generationDialogOpen && (
        <div
          className="modal-backdrop"
          role="presentation"
          onMouseDown={event => {
            if (event.target === event.currentTarget && !generating) setGenerationDialogOpen(false)
          }}
        >
          <section
            className="modal generation-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="chapter-generation-title"
          >
            <div className="modal-header">
              <h2 id="chapter-generation-title">智能生成章节正文</h2>
              <button
                className="icon-button"
                type="button"
                onClick={() => setGenerationDialogOpen(false)}
                aria-label="关闭章节生成弹窗"
                disabled={generating}
              >
                <X size={18} />
              </button>
            </div>
            <div className="modal-body generation-modal-body">
              <p className="generation-context-note">
                将按照章节规划中的本章目标字数（{planDraft.expected_words} 字）生成正文。
              </p>
              <label className="detail-edit-field">
                <span>你的想法（选填）</span>
                <textarea
                  value={generationIdea}
                  onChange={event => setGenerationIdea(event.target.value)}
                  rows={5}
                  maxLength={5000}
                  aria-label="章节生成想法"
                  placeholder="例如：重点描写主角第一次进入遗迹时的紧张感，并在结尾留下新的线索。"
                />
              </label>
              {generating && (
                <p className="form-message" role="status">
                  正在生成正文…已接收约 {generationProgress}%
                </p>
              )}
              {generationError && (
                <p className="form-message error" role="alert">
                  {generationError}
                </p>
              )}
              <div className="modal-actions">
                <button
                  className="secondary-button"
                  type="button"
                  onClick={() => setGenerationDialogOpen(false)}
                  disabled={generating}
                >
                  取消
                </button>
                <button
                  className="primary-button"
                  type="button"
                  onClick={() => void generateChapterContent()}
                  disabled={generating}
                >
                  <Sparkles size={15} />
                  {generating ? '正在生成…' : '生成章节'}
                </button>
              </div>
            </div>
          </section>
        </div>
      )}
    </div>
  )
}
