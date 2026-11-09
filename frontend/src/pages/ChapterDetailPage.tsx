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
import type { Chapter, ChapterMemory, ChapterPlan, ChapterVersion, GenerationJob, KnowledgeCitation } from '../types'
import { KnowledgeBaseSelector } from '../components/KnowledgeBaseSelector'
import { KnowledgeCitationList } from '../components/KnowledgeCitationList'
import { DraftRecoveryBanner } from '../components/DraftRecoveryBanner'
import { useDraftProtection } from '../hooks/useDraftProtection'

function formatChapterPlan(plan?: ChapterPlan | null) {
  if (!plan) return ''
  return [
    plan.objective && `本章目标：${plan.objective}`,
    plan.conflict && `核心冲突：${plan.conflict}`,
    plan.key_events && `关键情节：${plan.key_events}`,
    plan.ending_hook && `结尾钩子：${plan.ending_hook}`,
  ]
    .filter(Boolean)
    .join('\n')
}

function parseChapterPlan(text: string, expectedWords: number, current: ChapterPlan): ChapterPlan {
  const fields: Record<string, string> = {}
  const labels: Record<string, string> = {
    本章目标: 'objective',
    核心冲突: 'conflict',
    关键情节: 'key_events',
    结尾钩子: 'ending_hook',
  }
  let activeField = ''
  for (const line of text.split('\n')) {
    const match = line.match(/^(本章目标|核心冲突|关键情节|结尾钩子)[：:]\s*(.*)$/)
    if (match) {
      activeField = labels[match[1]]
      fields[activeField] = match[2]
    } else if (activeField) {
      fields[activeField] += `${fields[activeField] ? '\n' : ''}${line}`
    }
  }
  if (!Object.keys(fields).length) {
    const outline = text.trim()
    return {
      objective: outline.slice(0, 2000),
      conflict: current.conflict || '围绕本章细纲推进主要冲突',
      key_events: outline.slice(0, 10000),
      ending_hook: current.ending_hook || '按本章细纲安排结尾钩子',
      expected_words: expectedWords,
    }
  }
  return {
    objective: fields.objective || current.objective || '围绕本章细纲展开剧情',
    conflict: fields.conflict || current.conflict || '围绕本章细纲推进主要冲突',
    key_events: fields.key_events || current.key_events || text.trim(),
    ending_hook: fields.ending_hook || current.ending_hook || '按本章细纲安排结尾钩子',
    expected_words: expectedWords,
  }
}

export function ChapterDetailPage() {
  const { projectId, chapterId, feature } = useParams()
  const location = useLocation()
  const navigate = useNavigate()
  const { state: routeState } = location
  const [chapter, setChapter] = useState<Chapter | null>(null)
  const [loadedChapterKey, setLoadedChapterKey] = useState<string | null>(null)
  const [draft, setDraft] = useState({ chapter_number: '', chaptername: '', content: '' })
  const [planDraft, setPlanDraft] = useState<ChapterPlan>({
    objective: '',
    conflict: '',
    key_events: '',
    ending_hook: '',
    expected_words: 3000,
  })
  const [planTextDraft, setPlanTextDraft] = useState('')
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
  const [expandedReviewJobs, setExpandedReviewJobs] = useState<Set<string>>(new Set())
  const [historyLoading, setHistoryLoading] = useState(false)
  const [historyOpen, setHistoryOpen] = useState(false)
  const [versions, setVersions] = useState<ChapterVersion[]>([])
  const [compareVersionId, setCompareVersionId] = useState<number | null>(null)
  const [versionsOpen, setVersionsOpen] = useState(false)
  const [versionsLoading, setVersionsLoading] = useState(false)
  const [restoringVersion, setRestoringVersion] = useState<number | null>(null)
  const [retryingJob, setRetryingJob] = useState<string | null>(null)
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const [knowledgeBaseIds, setKnowledgeBaseIds] = useState<number[]>([])
  const [knowledgeCitations, setKnowledgeCitations] = useState<KnowledgeCitation[]>([])
  const [pendingVolumeProgress, setPendingVolumeProgress] = useState<{
    volumeId: number | null
    complete: boolean
    note: string | null
  } | null>(null)

  const chapterDraft = { draft, planDraft, planTextDraft, summaryDraft, memoryDraft, pendingVolumeProgress }
  const savedChapterDraft = {
    draft: {
      chapter_number: chapter ? String(chapter.chapter_number) : '',
      chaptername: chapter?.chaptername || '',
      content: chapter?.content || '',
    },
    planDraft: chapter?.plan || { objective: '', conflict: '', key_events: '', ending_hook: '', expected_words: 3000 },
    planTextDraft: formatChapterPlan(chapter?.plan),
    summaryDraft: chapter?.summary || '',
    memoryDraft: chapter?.memory || null,
    pendingVolumeProgress: null,
  }
  const draftProtection = useDraftProtection(
    projectId && chapterId ? `novel-agent:draft:chapter:${projectId}:${chapterId}` : null,
    chapterDraft,
    savedChapterDraft,
    Boolean(chapter && loadedChapterKey === `${projectId}:${chapterId}` && !loading),
    editing,
  )

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
    setPlanTextDraft(formatChapterPlan(value.plan))
    setSummaryDraft(value.summary || '')
    setMemoryDraft(value.memory || null)
  }, [chapterId, projectId])

  useEffect(() => {
    setLoading(true)
    setLoadedChapterKey(null)
    setError('')
    void loadChapter()
      .then(() => setLoadedChapterKey(`${projectId}:${chapterId}`))
      .catch(reason => setError(reason instanceof Error ? reason.message : '章节加载失败，请稍后重试'))
      .finally(() => setLoading(false))
  }, [chapterId, loadChapter, projectId])

  useEffect(() => {
    if (draftProtection.recovery) {
      if (feature === 'edit' || feature === 'plan' || feature === 'generate') setEditing(false)
      setPlanGenerationOpen(false)
      setGenerationDialogOpen(false)
    } else if (feature === 'edit' || feature === 'plan' || feature === 'generate') {
      setEditing(true)
    }
    const restoreState = routeState as { generatedContent?: string; plan?: ChapterPlan | null } | null
    if (!draftProtection.recovery && feature === 'edit' && restoreState?.generatedContent) {
      setEditing(true)
      setDraft(current => ({ ...current, content: restoreState.generatedContent || '' }))
      if (restoreState.plan) {
        setPlanDraft(restoreState.plan)
        setPlanTextDraft(formatChapterPlan(restoreState.plan))
      }
    }
    if (!draftProtection.recovery && feature === 'plan' && !loading) setPlanGenerationOpen(true)
    if (!draftProtection.recovery && feature === 'generate' && !loading) setGenerationDialogOpen(true)
    if (feature === 'history') setHistoryOpen(true)
    if (feature === 'versions') setVersionsOpen(true)
  }, [draftProtection.recovery, feature, loading, routeState])

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

  function toggleReviewDetails(jobId: string) {
    setExpandedReviewJobs(current => {
      const next = new Set(current)
      if (next.has(jobId)) next.delete(jobId)
      else next.add(jobId)
      return next
    })
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
    if (!window.confirm(`确定恢复到第 ${version.version_number} 个版本吗？当前内容会自动保存为新版本，未保存的本地修改也会被覆盖。`)) return
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
      setPlanTextDraft(formatChapterPlan(restored.plan))
      setSummaryDraft(restored.summary || '')
      setMemoryDraft(restored.memory || null)
      setEditing(false)
      draftProtection.discardDraft()
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
    setPlanTextDraft(formatChapterPlan(chapter.plan))
    setSummaryDraft(chapter.summary || '')
    setMemoryDraft(chapter.memory || null)
    setNotice('')
    setEditing(true)
  }

  function cancelEditing() {
    if (draftProtection.hasUnsavedChanges && !window.confirm('放弃当前修改并删除本地暂存草稿吗？')) return
    if (chapter) {
      setDraft({
        chapter_number: String(chapter.chapter_number),
        chaptername: chapter.chaptername || '',
        content: chapter.content || '',
      })
      setPlanDraft(
        chapter.plan || { objective: '', conflict: '', key_events: '', ending_hook: '', expected_words: 3000 },
      )
      setPlanTextDraft(formatChapterPlan(chapter.plan))
      setSummaryDraft(chapter.summary || '')
      setMemoryDraft(chapter.memory || null)
    }
    setEditing(false)
    draftProtection.discardDraft()
    setNotice('')
  }

  function restoreLocalDraft() {
    const recovered = draftProtection.recovery?.data
    if (!recovered) return
    setDraft(recovered.draft)
    setPlanDraft(recovered.planDraft)
    setPlanTextDraft(recovered.planTextDraft)
    setSummaryDraft(recovered.summaryDraft)
    setMemoryDraft(recovered.memoryDraft)
    setPendingVolumeProgress(recovered.pendingVolumeProgress)
    setEditing(true)
    draftProtection.dismissRecovery()
    setNotice('已恢复本地草稿；保存修改后会同步到作品')
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
      const parsedPlan = parseChapterPlan(planTextDraft, planDraft.expected_words, planDraft)
      const plan = planTextDraft.trim() ? parsedPlan : chapter.plan ? null : undefined
      const contentChanged = draft.content !== (chapter.content || '')
      const summaryChanged = summaryDraft !== (chapter.summary || '')
      const memoryChanged = JSON.stringify(memoryDraft) !== JSON.stringify(chapter.memory || null)
      const shouldRefreshMemory =
        Boolean(draft.content.trim()) && (contentChanged || !chapter.summary) && !summaryChanged && !memoryChanged
      const updated = await api.updateChapter(chapter.project_id, chapter.id, {
        chapter_number: number,
        chaptername: draft.chaptername.trim(),
        content: draft.content,
        ...(pendingVolumeProgress
          ? {
              volume_id: pendingVolumeProgress.volumeId,
              volume_complete: pendingVolumeProgress.complete,
              volume_completion_note: pendingVolumeProgress.note,
            }
          : {}),
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
      draftProtection.discardDraft()
      setNotice(
        pendingVolumeProgress?.complete
          ? '章节已保存，模型判断本卷目标已完成；后续细纲将进入下一卷。'
          : '章节修改已保存',
      )
      setPendingVolumeProgress(null)
      if (shouldRefreshMemory) setNotice('章节已保存，摘要和前文记忆将在后台整理')
    } catch (reason) {
      setNotice(reason instanceof Error ? reason.message : '章节保存失败，请稍后重试')
    } finally {
      setSaving(false)
    }
  }

  async function generateChapterPlan() {
    if (!chapter) return
    if (planTextDraft !== formatChapterPlan(chapter.plan)) {
      if (!window.confirm('生成新细纲会替换当前未保存的细纲；系统会先尝试暂存当前内容。确定继续吗？')) return
      if (!draftProtection.persistNow()) {
        setGenerationError('本地暂存失败，已取消生成以保护当前修改。请先复制或保存当前内容后重试。')
        return
      }
    }
    const words = Number(planDraft.expected_words)
    if (!Number.isInteger(words) || words <= 0 || words > 100000) {
      setGenerationError('请输入 1 到 100000 之间的本章目标字数')
      return
    }
    setPlanGenerating(true)
    setGenerationError('')
    try {
      const result = knowledgeBaseIds.length
        ? await api.generateChapterPlan(chapter.project_id, chapter.id, words, planGenerationIdea, knowledgeBaseIds)
        : await api.generateChapterPlan(chapter.project_id, chapter.id, words, planGenerationIdea)
      setPlanDraft(result.plan)
      setPlanTextDraft(formatChapterPlan(result.plan))
      setPendingVolumeProgress({
        volumeId: result.volume_id ?? null,
        complete: result.volume_complete === true,
        note: result.volume_completion_note || null,
      })
      setKnowledgeCitations(result.citations || [])
      setPlanGenerationOpen(false)
      setNotice(
        result.volume_complete
          ? `本章细纲已生成，模型判断本卷目标已完成；保存后才会进入下一卷。${result.volume_completion_note ? `依据：${result.volume_completion_note}` : ''}`
          : '本章细纲已生成，请检查后保存章节',
      )
    } catch (reason) {
      setGenerationError(reason instanceof Error ? reason.message : '本章细纲生成失败，请稍后重试')
    } finally {
      setPlanGenerating(false)
    }
  }

  async function generateChapterContent() {
    if (!chapter) return
    if (draft.content !== (chapter.content || '')) {
      if (!window.confirm('生成正文会替换当前未保存的正文；系统会先尝试暂存当前内容。确定继续吗？')) return
      if (!draftProtection.persistNow()) {
        setGenerationError('本地暂存失败，已取消生成以保护当前正文。请先复制或保存当前内容后重试。')
        return
      }
    }
    const words = Number(planDraft.expected_words)
    if (!Number.isInteger(words) || words <= 0 || words > 100000) {
      setGenerationError('请输入 1 到 100000 之间的本章目标字数')
      return
    }
    if (!planTextDraft.trim()) {
      setGenerationError('请先填写或生成完整的本章细纲')
      return
    }
    setGenerating(true)
    setGenerationProgress(0)
    setGenerationError('')
    setDraft(current => ({ ...current, content: '' }))
    try {
      const plan = parseChapterPlan(planTextDraft, words, planDraft)
      const streamGenerator = (
        api as typeof api & { generateChapterContentStream?: typeof api.generateChapterContentStream }
      ).generateChapterContentStream
      const onChunk = (chunk: string) => {
        setGenerationProgress(current =>
          Math.min(99, current + Math.max(1, Math.round((chunk.length / Math.max(1, words)) * 100))),
        )
        setDraft(current => ({ ...current, content: current.content + chunk }))
      }
      const result =
        typeof streamGenerator === 'function'
          ? knowledgeBaseIds.length
            ? await streamGenerator(chapter.project_id, chapter.id, plan, generationIdea, onChunk, knowledgeBaseIds)
            : await streamGenerator(chapter.project_id, chapter.id, plan, generationIdea, onChunk)
          : knowledgeBaseIds.length
            ? await api.generateChapterContent(chapter.project_id, chapter.id, plan, generationIdea, knowledgeBaseIds)
            : await api.generateChapterContent(chapter.project_id, chapter.id, plan, generationIdea)
      setDraft(current => ({ ...current, content: result.content }))
      setKnowledgeCitations(result.citations || [])
      setGenerationDialogOpen(false)
      setNotice(
        result.review_enabled
          ? `章节正文已生成，评论员最终评分 ${result.review_final_score ?? '未评分'} 分（${result.review_rounds ?? 0} 轮），请检查后点击“保存修改”入库`
          : '章节正文已生成，请检查后点击“保存修改”入库',
      )
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
                          {job.generation_info && (
                            <small>
                              Prompt {job.generation_info.prompt_template_id} v
                              {job.generation_info.prompt_template_version} · {job.generation_info.segments ?? 1} 段 ·
                              质量检查通过
                            </small>
                          )}
                          {job.generation_info?.review_enabled && (
                            <>
                              <small>
                                评论员评审：{job.generation_info.review_final_score ?? '未评分'} 分 ·{' '}
                                {job.generation_info.review_rounds ?? 0} 轮 ·{' '}
                                {job.generation_info.review_stop_reason === 'threshold_reached'
                                  ? '达到阈值'
                                  : job.generation_info.review_stop_reason === 'review_unavailable'
                                    ? '评论员不可用，保留初稿'
                                    : '达到轮次上限'}
                                {job.generation_info.review_error ? ` · ${job.generation_info.review_error}` : ''}
                              </small>
                              {job.generation_info.review_history && job.generation_info.review_history.length > 0 && (
                                <button
                                  className="text-button review-details-toggle"
                                  type="button"
                                  onClick={() => toggleReviewDetails(job.job_id)}
                                  aria-expanded={expandedReviewJobs.has(job.job_id)}
                                >
                                  {expandedReviewJobs.has(job.job_id) ? '收起评审详情' : '查看评审详情'}
                                </button>
                              )}
                            </>
                          )}
                          {job.generation_info?.review_enabled &&
                            expandedReviewJobs.has(job.job_id) &&
                            job.generation_info.review_history && (
                              <div className="review-history-details">
                                {job.generation_info.review_history.map(iteration => (
                                  <section className="review-iteration" key={`${job.job_id}-${iteration.round}`}>
                                    <div className="review-iteration-heading">
                                      <strong>第 {iteration.round} 轮评审</strong>
                                      <span>{iteration.score} 分</span>
                                    </div>
                                    <p>{iteration.review.summary}</p>
                                    {Object.keys(iteration.review.dimension_scores).length > 0 && (
                                      <div className="review-dimension-list">
                                        {Object.entries(iteration.review.dimension_scores).map(([name, score]) => (
                                          <span key={name}>{name}：{score}</span>
                                        ))}
                                      </div>
                                    )}
                                    {iteration.review.issues.length > 0 && (
                                      <ul className="review-issue-list">
                                        {iteration.review.issues.map(issue => (
                                          <li key={issue.id}>
                                            <strong>{issue.must_fix ? '必须修复 · ' : ''}{issue.suggestion}</strong>
                                            <span>{issue.evidence}</span>
                                          </li>
                                        ))}
                                      </ul>
                                    )}
                                  </section>
                                ))}
                              </div>
                            )}
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
                  {compareVersionId !== null &&
                    chapter &&
                    (() => {
                      const compared = versions.find(version => version.id === compareVersionId)
                      if (!compared) return null
                      const fields = [
                        {
                          label: '章节名称',
                          oldValue: compared.chaptername || '',
                          newValue: chapter.chaptername || '',
                        },
                        {
                          label: '章节编号',
                          oldValue: String(compared.chapter_number),
                          newValue: String(chapter.chapter_number),
                        },
                        { label: '正文', oldValue: compared.content || '', newValue: chapter.content || '' },
                        {
                          label: '章节细纲',
                          oldValue: JSON.stringify(compared.plan || null, null, 2) || '',
                          newValue: JSON.stringify(chapter.plan || null, null, 2) || '',
                        },
                        { label: '摘要', oldValue: compared.summary || '', newValue: chapter.summary || '' },
                        {
                          label: '章节记忆',
                          oldValue: JSON.stringify(compared.memory || null, null, 2) || '',
                          newValue: JSON.stringify(chapter.memory || null, null, 2) || '',
                        },
                      ]
                      const changedCount = fields.filter(field => field.oldValue !== field.newValue).length
                      return (
                        <section className="chapter-version-comparison" aria-label="版本对比">
                          <div className="section-heading">
                            <div>
                              <h2>版本 {compared.version_number} 与当前章节对比</h2>
                              <p>{changedCount === 0 ? '两个版本内容一致' : `${changedCount} 项内容有变化`}</p>
                            </div>
                            <button className="text-link" type="button" onClick={() => setCompareVersionId(null)}>
                              关闭对比
                            </button>
                          </div>
                          {fields
                            .filter(field => field.oldValue !== field.newValue)
                            .map(field => (
                              <div className="chapter-version-diff" key={field.label}>
                                <h3>{field.label}</h3>
                                <div>
                                  <section>
                                    <strong>版本 {compared.version_number}</strong>
                                    <pre>{field.oldValue || '（空）'}</pre>
                                  </section>
                                  <section>
                                    <strong>当前章节</strong>
                                    <pre>{field.newValue || '（空）'}</pre>
                                  </section>
                                </div>
                              </div>
                            ))}
                        </section>
                      )
                    })()}
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
                            onClick={() => setCompareVersionId(compareVersionId === version.id ? null : version.id)}
                          >
                            {compareVersionId === version.id ? '关闭对比' : '与当前版本对比'}
                          </button>
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

  const displayedContent = editing ? draft.content : chapter.content || ''

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
          {draftProtection.recovery && (
            <DraftRecoveryBanner
              savedAt={draftProtection.recovery.savedAt}
              onRestore={restoreLocalDraft}
              onDiscard={() => {
                draftProtection.discardDraft()
                setNotice('本地草稿已丢弃')
              }}
            />
          )}
          <div className="detail-page-toolbar">
            {draftProtection.status && (
              <span className="local-draft-status" role="status">
                {draftProtection.status === 'saving'
                  ? '正在暂存本地草稿…'
                  : draftProtection.status === 'saved'
                    ? `本地草稿已暂存${draftProtection.savedAt ? ` · ${new Date(draftProtection.savedAt).toLocaleTimeString()}` : ''}`
                    : '本地暂存不可用，请保存修改到作品'}
              </span>
            )}
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
              <button
                className="primary-button"
                type="button"
                onClick={beginEditing}
                disabled={Boolean(draftProtection.recovery)}
              >
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
                <span>本章细纲</span>
                {editing && (
                  <button
                    className="secondary-button"
                    type="button"
                    onClick={() => {
                      setPlanGenerationIdea('')
                      setGenerationError('')
                      setPlanGenerationOpen(true)
                    }}
                    disabled={planGenerating || saving}
                  >
                    <Sparkles size={15} />
                    智能生成细纲
                  </button>
                )}
              </div>
              {editing ? (
                <div className="detail-edit-field chapter-outline-field">
                  <textarea
                    value={planTextDraft}
                    onChange={event => setPlanTextDraft(event.target.value)}
                    rows={10}
                    aria-label="本章细纲"
                    placeholder="填写本章细纲，或使用智能生成。"
                  />
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
                <p className="chapter-plan-empty">尚未制定本章细纲。</p>
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
                    按细纲生成正文
                  </button>
                )}
              </div>
              <div className="chapter-content-editor">
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
                <span className="chapter-content-word-count" aria-live="polite">
                  {displayedContent.length} 字
                </span>
              </div>
            </div>
          </section>
        </div>
      </div>
      <KnowledgeCitationList citations={knowledgeCitations} />
      {planGenerationOpen && (
        <div className="modal-backdrop" role="presentation">
          <section
            className="modal generation-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="chapter-plan-generation-title"
          >
            <div className="modal-header">
              <h2 id="chapter-plan-generation-title">智能生成本章细纲</h2>
              <button
                className="icon-button"
                type="button"
                onClick={() => setPlanGenerationOpen(false)}
                aria-label="关闭细纲生成弹窗"
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
                  aria-label="本章细纲目标字数"
                />
              </label>
              <label className="detail-edit-field">
                <span>你的想法（选填）</span>
                <textarea
                  value={planGenerationIdea}
                  onChange={event => setPlanGenerationIdea(event.target.value)}
                  rows={5}
                  maxLength={5000}
                  aria-label="细纲生成想法"
                  placeholder="例如：本章让主角第一次进入遗迹，并在结尾发现敌人留下的信号。"
                />
              </label>
              <KnowledgeBaseSelector selectedIds={knowledgeBaseIds} onChange={setKnowledgeBaseIds} />
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
                  {planGenerating ? '正在生成…' : '生成细纲'}
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
                将按照本章细纲中的目标字数（{planDraft.expected_words} 字）生成正文。
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
              <KnowledgeBaseSelector selectedIds={knowledgeBaseIds} onChange={setKnowledgeBaseIds} />
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
