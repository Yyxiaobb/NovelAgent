import { ArrowLeft, BookOpenText, CalendarDays, Check, Edit3, FileText, Plus, Save, Trash2, X } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api } from '../api/client'
import { ChapterActionDialog } from '../components/ChapterActionDialog'
import { ProjectActionDialog } from '../components/ProjectActionDialog'
import type { Chapter, Project } from '../types'

const numberFormat = new Intl.NumberFormat('zh-CN')
const dateFormat = new Intl.DateTimeFormat('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' })
const projectTypes = ['玄幻', '都市', '言情', '悬疑', '科幻', '历史', '武侠', '现实', '灵异', '同人', '儿童', '其他']
const projectStatuses = ['连载中', '完结', '断更'] as const

function chapterTitle(chapter: Chapter) {
  return chapter.chaptername || `第 ${chapter.chapter_number} 章`
}

interface ChapterDraft {
  chapter_number: number
  chaptername: string
}

export function ProjectDetailPage() {
  const { projectId } = useParams()
  const navigate = useNavigate()
  const [project, setProject] = useState<Project | null>(null)
  const [chapters, setChapters] = useState<Chapter[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [editing, setEditing] = useState(false)
  const [savingProject, setSavingProject] = useState(false)
  const [projectDraft, setProjectDraft] = useState({ name: '', introduction: '', projectType: '', coverUrl: '', status: '连载中' as typeof projectStatuses[number] })
  const [chapterDrafts, setChapterDrafts] = useState<Record<number, ChapterDraft>>({})
  const [editingChapterIds, setEditingChapterIds] = useState<Set<number>>(new Set())
  const [chapterSaving, setChapterSaving] = useState<number | null>(null)
  const [newChapter, setNewChapter] = useState<ChapterDraft | null>(null)
  const [newChapterSaving, setNewChapterSaving] = useState(false)
  const [chapterToRecycle, setChapterToRecycle] = useState<Chapter | null>(null)
  const [recycleProjectOpen, setRecycleProjectOpen] = useState(false)

  const beginEditing = useCallback((detail: Project, chapterList: Chapter[]) => {
    setProjectDraft({
      name: detail.projectname || '',
      introduction: detail.introduction || '',
      projectType: detail.project_type || '',
      coverUrl: detail.cover_url || '',
      status: (detail.status === '完结' || detail.status === '断更' ? detail.status : '连载中'),
    })
    setChapterDrafts(Object.fromEntries(chapterList.map((chapter) => [chapter.id, {
      chapter_number: chapter.chapter_number,
      chaptername: chapter.chaptername || '',
    }])))
    setNewChapter(null)
  }, [])

  const refreshDetail = useCallback(async () => {
    const id = Number(projectId)
    if (!Number.isInteger(id) || id <= 0) {
      throw new Error('作品编号无效')
    }
    const [detail, chapterList] = await Promise.all([api.getProject(id), api.getProjectChapters(id)])
    setProject(detail)
    setChapters(chapterList)
    beginEditing(detail, chapterList)
    return { detail, chapterList }
  }, [beginEditing, projectId])

  const loadDetail = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      await refreshDetail()
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '作品详情加载失败，请稍后重试')
    } finally {
      setLoading(false)
    }
  }, [refreshDetail])

  useEffect(() => { void loadDetail() }, [loadDetail])

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
    setSavingProject(true)
    setNotice('')
    try {
      await api.updateProject(project.id, {
        projectname: projectDraft.name.trim(),
        introduction: projectDraft.introduction.trim(),
        project_type: projectDraft.projectType,
        cover_url: projectDraft.coverUrl.trim() || null,
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
      })
      await refreshDetail()
      setEditingChapterIds((current) => {
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
    if (!Number.isInteger(newChapter.chapter_number) || newChapter.chapter_number <= 0 || !newChapter.chaptername.trim()) {
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
      setChapters((current) => [...current, created].sort((left, right) => left.chapter_number - right.chapter_number))
      setChapterDrafts((current) => ({ ...current, [created.id]: { chapter_number: created.chapter_number, chaptername: created.chaptername || '' } }))
      setProject((current) => current ? { ...current, chapter_count: current.chapter_count + 1 } : current)
      setNewChapter(null)
      setNotice('章节已新增')
    } catch (reason) {
      setNotice(reason instanceof Error ? reason.message : '章节新增失败，请稍后重试')
    } finally {
      setNewChapterSaving(false)
    }
  }

  if (loading) return <div className="page"><div className="project-detail-skeleton" aria-label="正在加载作品详情"><span /><span /><span /></div></div>

  if (error || !project) {
    return <div className="page"><div className="empty-state"><BookOpenText size={32} /><h3>{error || '作品不存在'}</h3><p>作品可能已被移入回收站，或暂时无法访问。</p><Link className="secondary-button" to="/projects"><ArrowLeft size={16} />返回作品列表</Link></div></div>
  }

  return (
    <div className="page">
      <div className="detail-back-row"><Link className="text-link" to="/projects"><ArrowLeft size={16} />返回作品列表</Link><div className="detail-header-actions">{editing ? <><button className="secondary-button" type="button" onClick={cancelEditing} disabled={savingProject || Boolean(chapterSaving) || newChapterSaving}><X size={15} />取消编辑</button><button className="primary-button" type="button" onClick={() => void saveProject()} disabled={savingProject || Boolean(chapterSaving) || newChapterSaving}><Save size={15} />{savingProject ? '正在保存…' : '保存修改'}</button></> : <button className="primary-button" type="button" onClick={() => setEditing(true)}><Edit3 size={15} />编辑作品</button>}</div></div>
      {notice && <div className="form-message success page-notice" role="status">{notice}</div>}
      <section className="project-detail-hero">
        <div className="project-detail-cover" aria-label="作品封面">
          {(editing ? projectDraft.coverUrl : project.cover_url) ? <img src={(editing ? projectDraft.coverUrl : project.cover_url) || ''} alt={`${project.projectname || '未命名作品'}封面`} /> : <div className="project-cover-placeholder"><BookOpenText size={42} /><strong>{(editing ? projectDraft.name : project.projectname || '未').slice(0, 1) || '未'}</strong><span>墨笺作品</span></div>}
          {editing && <label className="detail-cover-input"><span>封面地址</span><input value={projectDraft.coverUrl} onChange={(event) => setProjectDraft((current) => ({ ...current, coverUrl: event.target.value }))} placeholder="https://example.com/cover.jpg" aria-label="封面地址" /></label>}
        </div>
        <div className="project-detail-heading">
          <div className="project-card-top">{editing ? <select className="status-edit-select" value={projectDraft.status} onChange={(event) => setProjectDraft((current) => ({ ...current, status: event.target.value as typeof projectStatuses[number] }))} aria-label="作品状态">{projectStatuses.map((status) => <option key={status} value={status}>{status}</option>)}</select> : <span className={`status-badge ${project.status === '完结' ? 'done' : project.status === '断更' ? 'paused' : ''}`}>{project.status || '连载中'}</span>}<span className="project-updated"><CalendarDays size={14} />更新于 {dateFormat.format(new Date(project.updated_at))}</span></div>
          <p className="eyebrow">作品详情</p>
          {editing ? <><label className="detail-edit-field"><span>作品名称</span><input value={projectDraft.name} onChange={(event) => setProjectDraft((current) => ({ ...current, name: event.target.value }))} maxLength={20} aria-label="作品名称" /></label><label className="detail-edit-field"><span>作品类型</span><select value={projectDraft.projectType} onChange={(event) => setProjectDraft((current) => ({ ...current, projectType: event.target.value }))} aria-label="作品类型"><option value="">请选择作品类型</option>{projectTypes.map((type) => <option key={type} value={type}>{type}</option>)}</select></label><label className="detail-edit-field detail-introduction-field"><span>作品简介</span><textarea value={projectDraft.introduction} onChange={(event) => setProjectDraft((current) => ({ ...current, introduction: event.target.value }))} maxLength={500} rows={5} aria-label="作品简介" /></label></> : <><h1>{project.projectname || '未命名作品'}</h1><p className="project-detail-introduction">{project.introduction || '尚未填写作品简介'}</p></>}
          <div className="project-detail-meta"><span>{editing ? (projectDraft.projectType || '未设置类型') : (project.project_type || '未设置类型')}</span><span><FileText size={15} />{project.chapter_count} 章</span><span>{numberFormat.format(project.total_words)} 字</span></div>
        </div>
      </section>

      <section className="content-section outline-management-card">
        <div><p className="eyebrow">创作规划</p><h2>大纲管理</h2><p>{project.outline ? '已有大纲内容，点击进入查看或修改。' : '先梳理故事主线，再开始章节创作。'}</p></div>
        <Link className="secondary-button" to={`/projects/${project.id}/outline`}>进入大纲详情</Link>
      </section>

      <section className="content-section detail-chapters-section">
        <div className="section-heading"><div><h2>章节管理</h2><p>{editing ? '可以修改或删除章节。' : '查看章节并将不需要的章节移入回收站。'}</p></div><div className="section-heading-actions"><span className="result-count">共 {chapters.length} 章</span>{!newChapter && <button className="secondary-button" type="button" onClick={() => setNewChapter({ chapter_number: chapters.length ? Math.max(...chapters.map((item) => item.chapter_number)) + 1 : 1, chaptername: '' })}><Plus size={15} />新增章节</button>}</div></div>
        {newChapter && <div className="detail-chapter-list detail-new-chapter"><article className="detail-chapter-row detail-chapter-edit-row"><input type="number" min="1" value={newChapter.chapter_number} onChange={(event) => setNewChapter({ ...newChapter, chapter_number: Number(event.target.value) })} aria-label="新章节编号" /><input value={newChapter.chaptername} onChange={(event) => setNewChapter({ ...newChapter, chaptername: event.target.value })} placeholder="章节名称" aria-label="新章节名称" /><button className="primary-button" type="button" onClick={() => void addChapter()} disabled={newChapterSaving}><Check size={15} />{newChapterSaving ? '保存中…' : '保存章节'}</button><button className="icon-button" type="button" onClick={() => setNewChapter(null)} aria-label="取消新增章节"><X size={16} /></button></article></div>}
        {chapters.length === 0 && !newChapter ? <div className="empty-state compact"><FileText size={30} /><h3>还没有章节</h3><p>点击“新增章节”开始创作。</p></div> : <div className="detail-chapter-list">
          {chapters.map((chapter) => { const draft = chapterDrafts[chapter.id] || { chapter_number: chapter.chapter_number, chaptername: chapter.chaptername || '' }; const chapterEditing = editingChapterIds.has(chapter.id); return <article className="detail-chapter-row" key={chapter.id}><span className="chapter-number">{String(chapter.chapter_number).padStart(2, '0')}</span>{chapterEditing ? <><input type="number" min="1" value={draft.chapter_number} onChange={(event) => setChapterDrafts((current) => ({ ...current, [chapter.id]: { ...draft, chapter_number: Number(event.target.value) } }))} aria-label={`${chapterTitle(chapter)}编号`} /><input value={draft.chaptername} onChange={(event) => setChapterDrafts((current) => ({ ...current, [chapter.id]: { ...draft, chaptername: event.target.value } }))} aria-label={`${chapterTitle(chapter)}名称`} /><button className="secondary-button chapter-save-button" type="button" onClick={() => void saveChapter(chapter)} disabled={chapterSaving === chapter.id}><Check size={14} />{chapterSaving === chapter.id ? '保存中…' : '保存章节'}</button></> : <div className="chapter-view-copy"><Link to={`/projects/${project.id}/chapters/${chapter.id}`}><h3>{chapterTitle(chapter)}</h3><p>更新于 {dateFormat.format(new Date(chapter.updated_at))}</p></Link></div>}<button className="secondary-button chapter-edit-button" type="button" onClick={() => setEditingChapterIds((current) => { const next = new Set(current); next.add(chapter.id); return next })} disabled={chapterEditing || chapterSaving !== null}>修改</button><button className="icon-button chapter-delete-button" type="button" aria-label={`将${chapterTitle(chapter)}移入回收站`} onClick={() => setChapterToRecycle(chapter)}><Trash2 size={16} /></button></article> })}
        </div>}
      </section>

      <div className="detail-danger-actions"><button className="secondary-button danger-button" type="button" onClick={() => setRecycleProjectOpen(true)}><Trash2 size={15} />移入回收站</button></div>
      <ProjectActionDialog project={recycleProjectOpen ? project : null} action="recycle" onClose={() => setRecycleProjectOpen(false)} onSuccess={() => navigate('/projects')} />
      <ChapterActionDialog chapter={chapterToRecycle} action="recycle" onClose={() => setChapterToRecycle(null)} onSuccess={(chapter) => { setChapters((current) => current.filter((item) => item.id !== chapter.id)); setProject((current) => current ? { ...current, chapter_count: Math.max(0, current.chapter_count - 1) } : current); setChapterToRecycle(null); setNotice('章节已移入回收站') }} />
    </div>
  )
}
