import {
  ArrowLeft,
  BookOpenText,
  CalendarDays,
  Check,
  Download,
  Edit3,
  FileText,
  Plus,
  Save,
  Sparkles,
  Trash2,
  Upload,
  X,
} from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api } from '../api/client'
import { ChapterActionDialog } from '../components/ChapterActionDialog'
import { Modal } from '../components/Modal'
import { ProjectActionDialog } from '../components/ProjectActionDialog'
import type { Chapter, OutlineVolume, Project } from '../types'

const numberFormat = new Intl.NumberFormat('zh-CN')
const dateFormat = new Intl.DateTimeFormat('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' })
const projectTypes = ['玄幻', '都市', '言情', '悬疑', '科幻', '历史', '武侠', '现实', '灵异', '同人', '儿童', '其他']
const projectStatuses = ['连载中', '完结', '断更'] as const

function readFileAsDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result))
    reader.onerror = () => reject(new Error('读取图片失败，请重试'))
    reader.readAsDataURL(file)
  })
}

function chapterTitle(chapter: Chapter) {
  return chapter.chaptername || `第 ${chapter.chapter_number} 章`
}

interface ChapterDraft {
  chapter_number: number
  chaptername: string
  volume_id?: number | null
}

export function ProjectDetailPage() {
  const { projectId } = useParams()
  const navigate = useNavigate()
  const [project, setProject] = useState<Project | null>(null)
  const [chapters, setChapters] = useState<Chapter[]>([])
  const [outlineVolumes, setOutlineVolumes] = useState<OutlineVolume[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [editing, setEditing] = useState(false)
  const [savingProject, setSavingProject] = useState(false)
  const [stateDraft, setStateDraft] = useState('')
  const [currentStateOpen, setCurrentStateOpen] = useState(false)
  const [editingState, setEditingState] = useState(false)
  const [savingState, setSavingState] = useState(false)
  const [projectDraft, setProjectDraft] = useState({
    name: '',
    introduction: '',
    projectType: '',
    coverUrl: '',
    expectedWords: '1000000',
    status: '连载中' as (typeof projectStatuses)[number],
  })
  const [chapterDrafts, setChapterDrafts] = useState<Record<number, ChapterDraft>>({})
  const [editingChapterIds, setEditingChapterIds] = useState<Set<number>>(new Set())
  const [chapterSaving, setChapterSaving] = useState<number | null>(null)
  const [newChapter, setNewChapter] = useState<ChapterDraft | null>(null)
  const [newChapterSaving, setNewChapterSaving] = useState(false)
  const [exportingFormat, setExportingFormat] = useState<'markdown' | 'txt' | null>(null)
  const [exportDialogOpen, setExportDialogOpen] = useState(false)
  const [uploadingCover, setUploadingCover] = useState(false)
  const [generatingCover, setGeneratingCover] = useState(false)
  const [coverAuthorDialogOpen, setCoverAuthorDialogOpen] = useState(false)
  const [coverAuthorName, setCoverAuthorName] = useState('')
  const [coverAuthorError, setCoverAuthorError] = useState('')
  const [chapterToRecycle, setChapterToRecycle] = useState<Chapter | null>(null)
  const [recycleProjectOpen, setRecycleProjectOpen] = useState(false)
  const [expandedVolumeIds, setExpandedVolumeIds] = useState<Set<number>>(new Set())
  const [reviewPreferences, setReviewPreferences] = useState({ enabled: false, max_rounds: 3, accept_score: 85, manual_approval: false })
  const [savingReviewPreferences, setSavingReviewPreferences] = useState(false)

  const nextChapter = chapters.find(chapter => !(chapter.content || '').trim()) || chapters[chapters.length - 1]
  const currentVolume =
    outlineVolumes.find(volume => volume.id === nextChapter?.volume_id && !volume.is_completed) ||
    outlineVolumes.find(volume => !volume.is_completed)

  const beginEditing = useCallback((detail: Project, chapterList: Chapter[]) => {
    setProjectDraft({
      name: detail.projectname || '',
      introduction: detail.introduction || '',
      projectType: detail.project_type || '',
      coverUrl: detail.cover_url || '',
      expectedWords: String(detail.expected_words || 1000000),
      status: detail.status === '完结' || detail.status === '断更' ? detail.status : '连载中',
    })
    setChapterDrafts(
      Object.fromEntries(
        chapterList.map(chapter => [
          chapter.id,
          {
            chapter_number: chapter.chapter_number,
            chaptername: chapter.chaptername || '',
            volume_id: chapter.volume_id,
          },
        ]),
      ),
    )
    setNewChapter(null)
  }, [])

  const refreshDetail = useCallback(async () => {
    const id = Number(projectId)
    if (!Number.isInteger(id) || id <= 0) {
      throw new Error('作品编号无效')
    }
    const [detail, chapterList, volumes] = await Promise.all([
      api.getProject(id),
      api.getProjectChapters(id),
      api.getOutlineVolumes(id).catch(() => []),
    ])
    setProject(detail)
    setChapters(chapterList)
    setOutlineVolumes(volumes)
    setStateDraft(detail.current_state_markdown || '')
    const activeVolumeIds = new Set(volumes.map(volume => volume.id))
    setExpandedVolumeIds(current => {
      const next = new Set(current)
      volumes.forEach(volume => next.add(volume.id))
      if (chapterList.some(chapter => !chapter.volume_id || !activeVolumeIds.has(chapter.volume_id))) next.add(0)
      return next
    })
    beginEditing(detail, chapterList)
    return { detail, chapterList }
  }, [beginEditing, projectId])

  const loadDetail = useCallback(async () => {
    setLoading(true)
    setError('')
    setCurrentStateOpen(false)
    setEditingState(false)
    try {
      await refreshDetail()
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '作品详情加载失败，请稍后重试')
    } finally {
      setLoading(false)
    }
  }, [refreshDetail])

  useEffect(() => {
    void loadDetail()
  }, [loadDetail])

  useEffect(() => {
    const id = Number(projectId)
    if (!Number.isInteger(id) || id <= 0) return
    void Promise.all([api.getReviewPreferences(), api.getProjectReviewPreferences(id)])
      .then(([account, projectOverride]) => {
        setReviewPreferences({
          enabled: projectOverride.enabled ?? account.enabled,
          max_rounds: projectOverride.max_rounds ?? account.max_rounds,
          accept_score: projectOverride.accept_score ?? account.accept_score,
          manual_approval: projectOverride.manual_approval ?? account.manual_approval,
        })
      })
      .catch(() => undefined)
  }, [projectId])

  async function saveProjectReviewPreferences() {
    if (!project) return
    setSavingReviewPreferences(true)
    setNotice('')
    try {
      await api.updateProjectReviewPreferences(project.id, reviewPreferences)
      setNotice('作品评审偏好已保存，生成时将覆盖账户默认设置')
    } catch (reason) {
      setNotice(reason instanceof Error ? reason.message : '作品评审偏好保存失败')
    } finally {
      setSavingReviewPreferences(false)
    }
  }

  async function clearProjectReviewPreferences() {
    if (!project) return
    setSavingReviewPreferences(true)
    try {
      await api.updateProjectReviewPreferences(project.id, {
        enabled: null,
        max_rounds: null,
        accept_score: null,
        manual_approval: null,
      })
      const defaults = await api.getReviewPreferences()
      setReviewPreferences({
        enabled: defaults.enabled,
        max_rounds: defaults.max_rounds,
        accept_score: defaults.accept_score,
        manual_approval: defaults.manual_approval,
      })
      setNotice('已清除作品覆盖，恢复使用账户默认')
    } catch (reason) {
      setNotice(reason instanceof Error ? reason.message : '清除作品偏好失败')
    } finally {
      setSavingReviewPreferences(false)
    }
  }

  function cancelEditing() {
    if (project) beginEditing(project, chapters)
    setEditing(false)
    setNotice('')
  }

  async function saveProject() {
    if (!project) return
    if (projectDraft.name.trim().length < 2) {
      setNotice('作品名称至少需要 2 个字符')
      return
    }
    const expectedWords = Number(projectDraft.expectedWords)
    if (!Number.isInteger(expectedWords) || expectedWords <= 0 || expectedWords > 10000000) {
      setNotice('请输入 1 到 10000000 之间的作品目标字数')
      return
    }
    setSavingProject(true)
    setNotice('')
    try {
      await api.updateProject(project.id, {
        projectname: projectDraft.name.trim(),
        introduction: projectDraft.introduction.trim(),
        project_type: projectDraft.projectType,
        cover_url: projectDraft.coverUrl.trim() || null,
        expected_words: expectedWords,
        status: projectDraft.status,
      })
      await refreshDetail()
      setEditing(false)
      setNotice('作品信息已保存')
    } catch (reason) {
      setNotice(reason instanceof Error ? reason.message : '作品信息保存失败，请稍后重试')
    } finally {
      setSavingProject(false)
    }
  }

  async function saveCurrentState() {
    if (!project) return
    if (!stateDraft.trim()) {
      setNotice('当前状态文档不能为空')
      return
    }
    setSavingState(true)
    setNotice('')
    try {
      const saved = await api.updateProjectState(project.id, stateDraft)
      setProject(current => (current ? { ...current, current_state_markdown: saved.current_state_markdown } : current))
      setStateDraft(saved.current_state_markdown)
      setEditingState(false)
      setNotice('当前状态文档已保存')
    } catch (reason) {
      setNotice(reason instanceof Error ? reason.message : '当前状态保存失败，请稍后重试')
    } finally {
      setSavingState(false)
    }
  }

  async function saveChapter(chapter: Chapter) {
    const draft = chapterDrafts[chapter.id]
    if (!draft || !Number.isInteger(draft.chapter_number) || draft.chapter_number <= 0 || !draft.chaptername.trim()) {
      setNotice('章节编号和章节名称不能为空')
      return
    }
    setChapterSaving(chapter.id)
    setNotice('')
    try {
      await api.updateChapter(chapter.project_id, chapter.id, {
        chapter_number: draft.chapter_number,
        chaptername: draft.chaptername.trim(),
        content: chapter.content || '',
        ...(draft.volume_id !== undefined ? { volume_id: draft.volume_id } : {}),
      })
      await refreshDetail()
      setEditingChapterIds(current => {
        const next = new Set(current)
        next.delete(chapter.id)
        return next
      })
      setNotice('章节已保存')
    } catch (reason) {
      setNotice(reason instanceof Error ? reason.message : '章节保存失败，请稍后重试')
    } finally {
      setChapterSaving(null)
    }
  }

  async function addChapter() {
    if (!project || !newChapter) return
    if (
      !Number.isInteger(newChapter.chapter_number) ||
      newChapter.chapter_number <= 0 ||
      !newChapter.chaptername.trim()
    ) {
      setNotice('章节编号和章节名称不能为空')
      return
    }
    setNewChapterSaving(true)
    setNotice('')
    try {
      const created = await api.createChapter(project.id, {
        chapter_number: newChapter.chapter_number,
        chaptername: newChapter.chaptername.trim(),
      })
      setChapters(current => [...current, created].sort((left, right) => left.chapter_number - right.chapter_number))
      setChapterDrafts(current => ({
        ...current,
        [created.id]: {
          chapter_number: created.chapter_number,
          chaptername: created.chaptername || '',
          volume_id: created.volume_id,
        },
      }))
      setProject(current => (current ? { ...current, chapter_count: current.chapter_count + 1 } : current))
      setNewChapter(null)
      setNotice('章节已新增')
    } catch (reason) {
      setNotice(reason instanceof Error ? reason.message : '章节新增失败，请稍后重试')
    } finally {
      setNewChapterSaving(false)
    }
  }

  function renderChapterRow(chapter: Chapter) {
    if (!project) return null
    const draft = chapterDrafts[chapter.id] || {
      chapter_number: chapter.chapter_number,
      chaptername: chapter.chaptername || '',
      volume_id: chapter.volume_id,
    }
    const chapterEditing = editingChapterIds.has(chapter.id)
    return (
      <article className="detail-chapter-row" key={chapter.id}>
        <span className="chapter-number">{String(chapter.chapter_number).padStart(2, '0')}</span>
        {chapterEditing ? (
          <>
            <input
              type="number"
              min="1"
              value={draft.chapter_number}
              onChange={event =>
                setChapterDrafts(current => ({
                  ...current,
                  [chapter.id]: { ...draft, chapter_number: Number(event.target.value) },
                }))
              }
              aria-label={`${chapterTitle(chapter)}编号`}
            />
            <input
              value={draft.chaptername}
              onChange={event =>
                setChapterDrafts(current => ({
                  ...current,
                  [chapter.id]: { ...draft, chaptername: event.target.value },
                }))
              }
              aria-label={`${chapterTitle(chapter)}名称`}
            />
            <button
              className="secondary-button chapter-save-button"
              type="button"
              onClick={() => void saveChapter(chapter)}
              disabled={chapterSaving === chapter.id}
            >
              <Check size={14} />
              {chapterSaving === chapter.id ? '保存中…' : '保存章节'}
            </button>
          </>
        ) : (
          <div className="chapter-view-copy">
            <Link to={`/projects/${project.id}/chapters/${chapter.id}`}>
              <h3>{chapterTitle(chapter)}</h3>
              <p>更新于 {dateFormat.format(new Date(chapter.updated_at))}</p>
            </Link>
          </div>
        )}
        <button
          className="secondary-button chapter-edit-button"
          type="button"
          onClick={() => setEditingChapterIds(current => new Set(current).add(chapter.id))}
          disabled={chapterEditing || chapterSaving !== null}
        >
          修改
        </button>
        <button
          className="icon-button chapter-delete-button"
          type="button"
          aria-label={`将${chapterTitle(chapter)}移入回收站`}
          onClick={() => setChapterToRecycle(chapter)}
        >
          <Trash2 size={16} />
        </button>
      </article>
    )
  }

  async function exportProject(format: 'markdown' | 'txt') {
    if (!project) return
    setExportingFormat(format)
    setExportDialogOpen(false)
    setNotice('')
    try {
      const blob = await api.exportProject(project.id, format)
      const objectUrl = URL.createObjectURL(blob)
      const link = document.createElement('a')
      const safeName = [...(project.projectname || '未命名作品')]
        .map(character => (/[\\/:*?"<>|]/.test(character) || character.charCodeAt(0) < 32 ? '_' : character))
        .join('')
        .trim()
      link.href = objectUrl
      link.download = `${safeName || '未命名作品'}.${format === 'markdown' ? 'md' : 'txt'}`
      document.body.append(link)
      link.click()
      link.remove()
      window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000)
      setNotice(`作品已导出为 ${format === 'markdown' ? 'Markdown' : 'TXT'}`)
    } catch (reason) {
      setNotice(reason instanceof Error ? reason.message : '作品导出失败，请稍后重试')
    } finally {
      setExportingFormat(null)
    }
  }

  async function uploadCover(file?: File) {
    if (!file || !project) return
    if (!file.type.startsWith('image/')) {
      setNotice('请选择图片文件')
      return
    }
    if (file.size > 5 * 1024 * 1024) {
      setNotice('封面图片不能超过 5 MB')
      return
    }
    setUploadingCover(true)
    setNotice('')
    try {
      const uploaded = await api.uploadProjectCover(project.id, await readFileAsDataUrl(file), file.name)
      setProject(uploaded)
      setProjectDraft(current => ({ ...current, coverUrl: uploaded.cover_url || '' }))
      setNotice('作品封面已上传')
    } catch (reason) {
      setNotice(reason instanceof Error ? reason.message : '封面上传失败，请稍后重试')
    } finally {
      setUploadingCover(false)
    }
  }

  async function generateCover(authorName: string) {
    if (!project) return
    setGeneratingCover(true)
    setNotice('正在根据作品内容生成封面…')
    try {
      const generated = await api.generateProjectCover(project.id, authorName)
      setProject(generated)
      setProjectDraft(current => ({ ...current, coverUrl: generated.cover_url || '' }))
      setNotice('智能封面已生成')
    } catch (reason) {
      setNotice(reason instanceof Error ? reason.message : '智能封面生成失败，请稍后重试')
    } finally {
      setGeneratingCover(false)
    }
  }

  function openCoverAuthorDialog() {
    setCoverAuthorName('')
    setCoverAuthorError('')
    setCoverAuthorDialogOpen(true)
  }

  function confirmGenerateCover() {
    const authorName = coverAuthorName.trim()
    if (!authorName) {
      setCoverAuthorError('请输入作者名')
      return
    }
    setCoverAuthorError('')
    setCoverAuthorDialogOpen(false)
    void generateCover(authorName)
  }

  if (loading)
    return (
      <div className="page">
        <div className="project-detail-skeleton" aria-label="正在加载作品详情">
          <span />
          <span />
          <span />
        </div>
      </div>
    )

  if (error || !project) {
    return (
      <div className="page">
        <div className="empty-state">
          <BookOpenText size={32} />
          <h3>{error || '作品不存在'}</h3>
          <p>作品可能已被移入回收站，或暂时无法访问。</p>
          <Link className="secondary-button" to="/projects">
            <ArrowLeft size={16} />
            返回作品列表
          </Link>
        </div>
      </div>
    )
  }

  const activeVolumeIds = new Set(outlineVolumes.map(volume => volume.id))
  const contentWordCount = chapters.reduce(
    (sum, chapter) => sum + (chapter.word_count ?? chapter.content?.length ?? 0),
    0,
  )
  const unassignedChapters = chapters.filter(chapter => !chapter.volume_id || !activeVolumeIds.has(chapter.volume_id))

  return (
    <div className="page">
      <div className="detail-back-row">
        <Link className="text-link" to="/projects">
          <ArrowLeft size={16} />
          返回作品列表
        </Link>
        <div className="detail-header-actions">
          {editing ? (
            <>
              <button
                className="secondary-button"
                type="button"
                onClick={cancelEditing}
                disabled={savingProject || Boolean(chapterSaving) || newChapterSaving}
              >
                <X size={15} />
                取消编辑
              </button>
              <button
                className="primary-button"
                type="button"
                onClick={() => void saveProject()}
                disabled={savingProject || Boolean(chapterSaving) || newChapterSaving}
              >
                <Save size={15} />
                {savingProject ? '正在保存…' : '保存修改'}
              </button>
            </>
          ) : (
            <>
              <button
                className="secondary-button"
                type="button"
                onClick={() => setExportDialogOpen(true)}
                disabled={exportingFormat !== null}
              >
                <Download size={15} />
                {exportingFormat ? '正在导出…' : '导出'}
              </button>
              <button className="primary-button" type="button" onClick={() => setEditing(true)}>
                <Edit3 size={15} />
                编辑作品
              </button>
            </>
          )}
        </div>
      </div>
      {notice && (
        <div className="form-message success page-notice" role="status">
          {notice}
        </div>
      )}
      <section className="project-detail-hero">
        <div className="project-detail-cover-column">
          <div className="project-detail-cover" aria-label="作品封面">
            {(editing ? projectDraft.coverUrl : project.cover_url) ? (
              <img
                src={(editing ? projectDraft.coverUrl : project.cover_url) || ''}
                alt={`${project.projectname || '未命名作品'}封面`}
              />
            ) : (
              <div className="project-cover-placeholder">
                <BookOpenText size={42} />
                <strong>{(editing ? projectDraft.name : project.projectname || '未').slice(0, 1) || '未'}</strong>
                <span>墨笺作品</span>
              </div>
            )}
          </div>
          {editing && (
            <label className="detail-cover-input">
              <span>封面地址</span>
              <input
                value={projectDraft.coverUrl}
                onChange={event => setProjectDraft(current => ({ ...current, coverUrl: event.target.value }))}
                placeholder="https://example.com/cover.jpg"
                aria-label="封面地址"
              />
              <div className="cover-edit-actions">
                <label className="cover-upload-button">
                  <Upload size={13} />
                  {uploadingCover ? '上传中…' : '本地上传'}
                  <input
                    className="visually-hidden-file-input"
                    type="file"
                    accept="image/png,image/jpeg,image/webp,image/gif"
                    onChange={event => {
                      void uploadCover(event.target.files?.[0])
                      event.currentTarget.value = ''
                    }}
                    disabled={uploadingCover || generatingCover}
                    aria-label="本地上传作品封面"
                  />
                </label>
                <button
                  className="cover-generate-button"
                  type="button"
                  onClick={openCoverAuthorDialog}
                  disabled={uploadingCover || generatingCover}
                >
                  <Sparkles size={13} />
                  {generatingCover ? '生成中…' : '根据内容生成'}
                </button>
              </div>
              <small className="cover-input-hint">支持 PNG、JPG、WEBP、GIF，单张不超过 5 MB</small>
            </label>
          )}
        </div>
        <div className="project-detail-heading">
          <div className="project-card-top">
            {editing ? (
              <select
                className="status-edit-select"
                value={projectDraft.status}
                onChange={event =>
                  setProjectDraft(current => ({
                    ...current,
                    status: event.target.value as (typeof projectStatuses)[number],
                  }))
                }
                aria-label="作品状态"
              >
                {projectStatuses.map(status => (
                  <option key={status} value={status}>
                    {status}
                  </option>
                ))}
              </select>
            ) : (
              <span
                className={`status-badge ${project.status === '完结' ? 'done' : project.status === '断更' ? 'paused' : ''}`}
              >
                {project.status || '连载中'}
              </span>
            )}
            <span className="project-updated">
              <CalendarDays size={14} />
              更新于 {dateFormat.format(new Date(project.updated_at))}
            </span>
          </div>
          <p className="eyebrow">作品详情</p>
          {editing ? (
            <>
              <label className="detail-edit-field">
                <span>作品名称</span>
                <input
                  value={projectDraft.name}
                  onChange={event => setProjectDraft(current => ({ ...current, name: event.target.value }))}
                  maxLength={20}
                  aria-label="作品名称"
                />
              </label>
              <label className="detail-edit-field">
                <span>作品类型</span>
                <select
                  value={projectDraft.projectType}
                  onChange={event => setProjectDraft(current => ({ ...current, projectType: event.target.value }))}
                  aria-label="作品类型"
                >
                  <option value="">请选择作品类型</option>
                  {projectTypes.map(type => (
                    <option key={type} value={type}>
                      {type}
                    </option>
                  ))}
                </select>
              </label>
              <label className="detail-edit-field detail-introduction-field">
                <span>作品简介</span>
                <textarea
                  value={projectDraft.introduction}
                  onChange={event => setProjectDraft(current => ({ ...current, introduction: event.target.value }))}
                  maxLength={500}
                  rows={5}
                  aria-label="作品简介"
                />
              </label>
              <label className="detail-edit-field">
                <span>作品目标字数</span>
                <input
                  type="number"
                  min="1"
                  max="10000000"
                  value={projectDraft.expectedWords}
                  onChange={event => setProjectDraft(current => ({ ...current, expectedWords: event.target.value }))}
                  aria-label="作品目标字数"
                />
              </label>
            </>
          ) : (
            <>
              <h1>{project.projectname || '未命名作品'}</h1>
              <p className="project-detail-introduction">{project.introduction || '尚未填写作品简介'}</p>
            </>
          )}
          <div className="project-detail-meta">
            <span>{editing ? projectDraft.projectType || '未设置类型' : project.project_type || '未设置类型'}</span>
            <span>
              <FileText size={15} />
              {project.chapter_count} 章
            </span>
            <span>{numberFormat.format(contentWordCount)} 字</span>
          </div>
        </div>
      </section>

      <section className="creation-progress-grid" aria-label="创作进度">
        <article className="creation-progress-card">
          <span>正文进度</span>
          <strong>
            {numberFormat.format(contentWordCount)} / {numberFormat.format(project.expected_words || 1000000)} 字
          </strong>
          <div className="creation-progress-track">
            <span
              style={{
                width: `${Math.min(100, Math.round((contentWordCount * 100) / (project.expected_words || 1000000)))}%`,
              }}
            />
          </div>
          <small>
            {Math.min(100, (contentWordCount / (project.expected_words || 1000000)) * 100).toFixed(1)}% · 目标{' '}
            {numberFormat.format(project.expected_words || 1000000)} 字
          </small>
        </article>
        <article className="creation-progress-card">
          <span>章节细纲</span>
          <strong>
            {chapters.filter(item => item.plan).length} / {chapters.length} 章
          </strong>
          <small>已完成章节细纲 · {chapters.filter(item => !item.content).length} 章待写正文</small>
        </article>
        <article className="creation-progress-card">
          <span>创作规划</span>
          <strong>{currentVolume?.name || (project.outline ? '总纲已建立' : '总纲待完善')}</strong>
          <small>
            {nextChapter
              ? `当前推进：第${nextChapter.chapter_number}章 · ${nextChapter.chaptername || '未命名章节'}`
              : '建立总纲后创建章节细纲'}
          </small>
          {nextChapter && <Link to={`/projects/${project.id}/chapters/${nextChapter.id}`}>继续当前章节</Link>}
          <Link to={`/projects/${project.id}/outline`}>打开规划中心</Link>
        </article>
      </section>

      <section className="content-section project-review-settings">
        <div className="section-heading">
          <div>
            <p className="eyebrow">多智能体协作</p>
            <h2>作品评审偏好</h2>
            <p>此处设置仅覆盖当前作品；清除后恢复账户默认值。</p>
          </div>
        </div>
        <div className="project-review-controls">
          <label className="field"><span>评论员</span>
            <select value={reviewPreferences.enabled ? 'on' : 'off'} onChange={event => setReviewPreferences(value => ({ ...value, enabled: event.target.value === 'on' }))}>
              <option value="off">关闭</option><option value="on">启用</option>
            </select>
          </label>
          <label className="field"><span>评审轮数</span>
            <input type="number" min="1" max="3" value={reviewPreferences.max_rounds} onChange={event => setReviewPreferences(value => ({ ...value, max_rounds: Number(event.target.value) }))} />
          </label>
          <label className="field"><span>达标分数</span>
            <input type="number" min="0" max="100" value={reviewPreferences.accept_score} onChange={event => setReviewPreferences(value => ({ ...value, accept_score: Number(event.target.value) }))} />
          </label>
          <label className="checkbox-field">
            <input type="checkbox" checked={reviewPreferences.manual_approval} onChange={event => setReviewPreferences(value => ({ ...value, manual_approval: event.target.checked }))} />
            <span>人工审核：返回初稿和评审意见，不自动修订</span>
          </label>
        </div>
        <div className="section-heading-actions">
          <button className="secondary-button" type="button" onClick={() => void clearProjectReviewPreferences()} disabled={savingReviewPreferences}>使用账户默认</button>
          <button className="primary-button" type="button" onClick={() => void saveProjectReviewPreferences()} disabled={savingReviewPreferences}>{savingReviewPreferences ? '正在保存…' : '保存作品偏好'}</button>
        </div>
      </section>

      <section className="content-section project-state-section">
        {!currentStateOpen ? (
          <button className="secondary-button" type="button" onClick={() => setCurrentStateOpen(true)}>
            查看当前状态
          </button>
        ) : (
          <>
            <div className="section-heading">
              <div>
                <p className="eyebrow">故事连续性</p>
                <h2>当前状态</h2>
                <p>保存章节正文后，系统会在后台依据正文更新这份 Markdown 文档；完成后刷新本页查看。</p>
              </div>
              <div className="section-heading-actions">
                {editingState ? (
                  <>
                    <button
                      className="secondary-button"
                      type="button"
                      onClick={() => {
                        setStateDraft(project.current_state_markdown || '')
                        setEditingState(false)
                      }}
                      disabled={savingState}
                    >
                      <X size={15} />
                      取消
                    </button>
                    <button
                      className="primary-button"
                      type="button"
                      onClick={() => void saveCurrentState()}
                      disabled={savingState}
                    >
                      <Save size={15} />
                      {savingState ? '保存中…' : '保存状态'}
                    </button>
                  </>
                ) : (
                  <>
                    <button className="secondary-button" type="button" onClick={() => setEditingState(true)}>
                      <Edit3 size={15} />
                      编辑状态
                    </button>
                    <button className="secondary-button" type="button" onClick={() => setCurrentStateOpen(false)}>
                      收起
                    </button>
                  </>
                )}
              </div>
            </div>
            {editingState ? (
              <textarea
                className="project-state-editor"
                value={stateDraft}
                onChange={event => setStateDraft(event.target.value)}
                maxLength={20000}
                aria-label="当前状态 Markdown 文档"
                spellCheck={false}
              />
            ) : (
              <pre className="project-state-preview">{project.current_state_markdown || '当前状态文档尚未生成。'}</pre>
            )}
          </>
        )}
      </section>

      <section className="content-section outline-management-card">
        <div>
          <p className="eyebrow">创作规划</p>
          <h2>大纲管理</h2>
          <p>{project.outline ? '已有大纲内容，点击进入查看或修改。' : '先梳理故事主线，再开始章节创作。'}</p>
        </div>
        <Link className="secondary-button" to={`/projects/${project.id}/outline`}>
          进入大纲详情
        </Link>
        <Link className="secondary-button" to={`/projects/${project.id}/memories`}>
          管理长期记忆
        </Link>
      </section>

      <section className="content-section detail-chapters-section">
        <div className="section-heading">
          <div>
            <h2>章节管理</h2>
            <p>{editing ? '可以修改或删除章节。' : '查看章节并将不需要的章节移入回收站。'}</p>
          </div>
          <div className="section-heading-actions">
            <span className="result-count">共 {chapters.length} 章</span>
            {!newChapter && (
              <button
                className="secondary-button"
                type="button"
                onClick={() =>
                  setNewChapter({
                    chapter_number: chapters.length ? Math.max(...chapters.map(item => item.chapter_number)) + 1 : 1,
                    chaptername: '',
                  })
                }
              >
                <Plus size={15} />
                新增章节
              </button>
            )}
          </div>
        </div>
        {newChapter && (
          <div className="detail-chapter-list detail-new-chapter">
            <article className="detail-chapter-row detail-chapter-edit-row">
              <input
                type="number"
                min="1"
                value={newChapter.chapter_number}
                onChange={event => setNewChapter({ ...newChapter, chapter_number: Number(event.target.value) })}
                aria-label="新章节编号"
              />
              <input
                value={newChapter.chaptername}
                onChange={event => setNewChapter({ ...newChapter, chaptername: event.target.value })}
                placeholder="章节名称"
                aria-label="新章节名称"
              />
              <button
                className="primary-button"
                type="button"
                onClick={() => void addChapter()}
                disabled={newChapterSaving}
              >
                <Check size={15} />
                {newChapterSaving ? '保存中…' : '保存章节'}
              </button>
              <button
                className="icon-button"
                type="button"
                onClick={() => setNewChapter(null)}
                aria-label="取消新增章节"
              >
                <X size={16} />
              </button>
            </article>
          </div>
        )}
        {chapters.length === 0 && !newChapter ? (
          <div className="empty-state compact">
            <FileText size={30} />
            <h3>还没有章节</h3>
            <p>点击“新增章节”开始创作。</p>
          </div>
        ) : (
          <div className="detail-chapter-list">
            {outlineVolumes.map(volume => {
              const volumeChapters = chapters.filter(chapter => chapter.volume_id === volume.id)
              const expanded = expandedVolumeIds.has(volume.id)
              return (
                <section className="chapter-volume-group" key={volume.id}>
                  <button
                    className="chapter-volume-toggle"
                    type="button"
                    aria-expanded={expanded}
                    onClick={() =>
                      setExpandedVolumeIds(current => {
                        const next = new Set(current)
                        if (next.has(volume.id)) next.delete(volume.id)
                        else next.add(volume.id)
                        return next
                      })
                    }
                  >
                    <span>
                      <strong>第{volume.volume_number}卷</strong> {volume.name}
                    </span>
                    <small>
                      {volumeChapters.length} 章 · {expanded ? '收起' : '展开'}
                    </small>
                  </button>
                  {expanded && volumeChapters.map(renderChapterRow)}
                </section>
              )
            })}
            {unassignedChapters.length > 0 && (
              <section className="chapter-volume-group">
                <button
                  className="chapter-volume-toggle"
                  type="button"
                  aria-expanded={expandedVolumeIds.has(0)}
                  onClick={() =>
                    setExpandedVolumeIds(current => {
                      const next = new Set(current)
                      if (next.has(0)) next.delete(0)
                      else next.add(0)
                      return next
                    })
                  }
                >
                  <span>
                    <strong>未分卷</strong>
                  </span>
                  <small>
                    {unassignedChapters.length} 章 · {expandedVolumeIds.has(0) ? '收起' : '展开'}
                  </small>
                </button>
                {expandedVolumeIds.has(0) && unassignedChapters.map(renderChapterRow)}
              </section>
            )}
          </div>
        )}
      </section>

      <div className="detail-danger-actions">
        <button className="secondary-button danger-button" type="button" onClick={() => setRecycleProjectOpen(true)}>
          <Trash2 size={15} />
          移入回收站
        </button>
      </div>
      <Modal
        open={exportDialogOpen}
        title="选择导出格式"
        onClose={() => setExportDialogOpen(false)}
        busy={exportingFormat !== null}
      >
        <div className="modal-body export-format-body">
          <p className="export-format-help">选择一种格式下载当前作品及章节内容。</p>
          <div className="export-format-options">
            <button
              className="export-format-option"
              type="button"
              onClick={() => void exportProject('markdown')}
              disabled={exportingFormat !== null}
            >
              <span className="export-format-icon">
                <FileText size={19} />
              </span>
              <span>
                <strong>Markdown</strong>
                <small>适合继续编辑或发布到支持 Markdown 的平台</small>
              </span>
            </button>
            <button
              className="export-format-option"
              type="button"
              onClick={() => void exportProject('txt')}
              disabled={exportingFormat !== null}
            >
              <span className="export-format-icon">
                <FileText size={19} />
              </span>
              <span>
                <strong>TXT 纯文本</strong>
                <small>适合在各类阅读器和文字工具中打开</small>
              </span>
            </button>
          </div>
        </div>
      </Modal>
      <Modal
        open={coverAuthorDialogOpen}
        title="生成智能封面"
        onClose={() => setCoverAuthorDialogOpen(false)}
        busy={generatingCover}
      >
        <form
          className="modal-body form-stack"
          onSubmit={event => {
            event.preventDefault()
            confirmGenerateCover()
          }}
        >
          <p>封面将显示作者名，请确认后再开始生成。</p>
          <label className="field">
            <span>作者名</span>
            <input
              value={coverAuthorName}
              onChange={event => {
                setCoverAuthorName(event.target.value)
                if (coverAuthorError) setCoverAuthorError('')
              }}
              maxLength={50}
              placeholder="请输入作者名"
              aria-label="作者名"
              autoFocus
              required
            />
          </label>
          {coverAuthorError && (
            <div className="form-message error" role="alert">
              {coverAuthorError}
            </div>
          )}
          <div className="modal-actions">
            <button className="secondary-button" type="button" onClick={() => setCoverAuthorDialogOpen(false)}>
              取消
            </button>
            <button className="primary-button" type="submit">
              <Sparkles size={15} />
              确认生成
            </button>
          </div>
        </form>
      </Modal>
      <ProjectActionDialog
        project={recycleProjectOpen ? project : null}
        action="recycle"
        onClose={() => setRecycleProjectOpen(false)}
        onSuccess={() => navigate('/projects')}
      />
      <ChapterActionDialog
        chapter={chapterToRecycle}
        action="recycle"
        onClose={() => setChapterToRecycle(null)}
        onSuccess={chapter => {
          setChapters(current => current.filter(item => item.id !== chapter.id))
          setProject(current =>
            current ? { ...current, chapter_count: Math.max(0, current.chapter_count - 1) } : current,
          )
          setChapterToRecycle(null)
          setNotice('章节已移入回收站')
        }}
      />
    </div>
  )
}
