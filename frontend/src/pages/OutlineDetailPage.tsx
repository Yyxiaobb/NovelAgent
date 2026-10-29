import {
  ArrowLeft,
  BookOpenText,
  Edit3,
  PanelLeftClose,
  PanelLeftOpen,
  RotateCcw,
  Save,
  Sparkles,
  Trash2,
  X,
} from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../api/client'
import type {
  Chapter,
  ChapterVersion,
  Inspiration,
  KnowledgeCitation,
  OutlineVersion,
  OutlineVolume,
  OutlineVolumeVersion,
} from '../types'
import { KnowledgeBaseSelector } from '../components/KnowledgeBaseSelector'
import { KnowledgeCitationList } from '../components/KnowledgeCitationList'
import { InspirationSelector } from '../components/InspirationSelector'

export function OutlineDetailPage() {
  const { projectId, feature } = useParams()
  const [outline, setOutline] = useState('')
  const [draft, setDraft] = useState('')
  const [projectName, setProjectName] = useState('作品大纲')
  const [editing, setEditing] = useState(false)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [expectedWords, setExpectedWords] = useState('1000000')
  const [savedExpectedWords, setSavedExpectedWords] = useState('1000000')
  const [generationIdea, setGenerationIdea] = useState('')
  const [generationDialogOpen, setGenerationDialogOpen] = useState(false)
  const [generationError, setGenerationError] = useState('')
  const [inspirationItems, setInspirationItems] = useState<Inspiration[]>([])
  const [inspirationIds, setInspirationIds] = useState<number[]>([])
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [versions, setVersions] = useState<OutlineVersion[]>([])
  const [volumeVersions, setVolumeVersions] = useState<OutlineVolumeVersion[]>([])
  const [rollingVersions, setRollingVersions] = useState<ChapterVersion[]>([])
  const [versionTab, setVersionTab] = useState<'total' | 'volumes' | 'chapters'>('total')
  const [versionsOpen, setVersionsOpen] = useState(false)
  const [versionsLoading, setVersionsLoading] = useState(false)
  const [restoringVersion, setRestoringVersion] = useState<number | null>(null)
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const [knowledgeBaseIds, setKnowledgeBaseIds] = useState<number[]>([])
  const [knowledgeCitations, setKnowledgeCitations] = useState<KnowledgeCitation[]>([])
  const [activeLevel, setActiveLevel] = useState<'total' | 'volumes' | 'chapters'>('total')
  const [chapters, setChapters] = useState<Chapter[]>([])
  const [volumes, setVolumes] = useState<OutlineVolume[]>([])
  const [volumeEditing, setVolumeEditing] = useState<Record<number, boolean>>({})
  const [volumeLoading, setVolumeLoading] = useState(false)
  const [volumeSaving, setVolumeSaving] = useState<number | null>(null)
  const [volumeGenerating, setVolumeGenerating] = useState<number | null>(null)
  const [volumePlanGenerating, setVolumePlanGenerating] = useState(false)
  const [rollingPlanning, setRollingPlanning] = useState(false)
  const [rollingPlanProgress, setRollingPlanProgress] = useState('')
  const [volumeIdeas, setVolumeIdeas] = useState<Record<number, string>>({})
  const [volumeError, setVolumeError] = useState('')
  const [newVolumeDialogOpen, setNewVolumeDialogOpen] = useState(false)
  const [newVolumeDraft, setNewVolumeDraft] = useState({
    volume_number: '1',
    name: '',
    outline: '',
  })
  const firstUnwrittenChapter = chapters.findIndex(chapter => !(chapter.content || '').trim())
  const rollingChapters = chapters
    .slice(firstUnwrittenChapter < 0 ? chapters.length : firstUnwrittenChapter)
    .slice(0, 5)

  const loadOutline = useCallback(async () => {
    const id = Number(projectId)
    if (!Number.isInteger(id) || id <= 0) throw new Error('作品编号无效')
    const [value, project] = await Promise.all([api.getProjectOutline(id), api.getProject(id)])
    setOutline(value.outline || '')
    setDraft(value.outline || '')
    setProjectName(project.projectname || '作品大纲')
    const targetWords = String(project.expected_words || 1000000)
    setExpectedWords(targetWords)
    setSavedExpectedWords(targetWords)
  }, [projectId])

  useEffect(() => {
    const id = Number(projectId)
    if (!Number.isInteger(id) || id <= 0 || activeLevel === 'total') return
    let cancelled = false
    setVolumeLoading(true)
    const load = activeLevel === 'volumes' ? api.getOutlineVolumes(id) : api.getProjectChapters(id)
    void load
      .then(value => {
        if (cancelled) return
        if (activeLevel === 'volumes') setVolumes(value as OutlineVolume[])
        else setChapters(value as Chapter[])
        setVolumeError('')
      })
      .catch(reason => {
        if (!cancelled) setVolumeError(reason instanceof Error ? reason.message : '规划内容加载失败，请稍后重试')
      })
      .finally(() => {
        if (!cancelled) setVolumeLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [activeLevel, projectId])

  useEffect(() => {
    setLoading(true)
    setError('')
    void loadOutline()
      .catch(reason => setError(reason instanceof Error ? reason.message : '大纲加载失败，请稍后重试'))
      .finally(() => setLoading(false))
  }, [loadOutline])

  useEffect(() => {
    if (feature === 'edit' || feature === 'generate') setEditing(true)
    if (feature === 'generate' && !loading) setGenerationDialogOpen(true)
    if (feature === 'versions') setVersionsOpen(true)
  }, [feature, loading])

  const loadVersions = useCallback(async () => {
    const id = Number(projectId)
    if (!Number.isInteger(id) || id <= 0) return
    setVersionsLoading(true)
    try {
      if (versionTab === 'total') setVersions(await api.getOutlineVersions(id))
      else if (versionTab === 'volumes') setVolumeVersions(await api.getOutlineVolumeVersions(id))
      else setRollingVersions(await api.getRollingOutlineVersions(id))
    } catch {
      setNotice('大纲版本历史暂时无法加载')
    } finally {
      setVersionsLoading(false)
    }
  }, [projectId, versionTab])

  useEffect(() => {
    if (versionsOpen) void loadVersions()
  }, [versionsOpen, loadVersions])

  async function restoreVersion(version: OutlineVersion) {
    const id = Number(projectId)
    if (!Number.isInteger(id) || id <= 0) return
    if (!window.confirm(`确定恢复到第 ${version.version_number} 个版本吗？当前大纲会自动保存为新版本。`)) return
    setRestoringVersion(version.id)
    try {
      const restored = await api.restoreOutlineVersion(id, version.id)
      setOutline(restored.outline || '')
      setDraft(restored.outline || '')
      setEditing(false)
      setNotice(`已恢复第 ${version.version_number} 个大纲版本`)
      await loadVersions()
    } catch (reason) {
      setNotice(reason instanceof Error ? reason.message : '恢复大纲版本失败，请稍后重试')
    } finally {
      setRestoringVersion(null)
    }
  }

  async function restoreVolumeVersion(version: OutlineVolumeVersion) {
    const id = Number(projectId)
    if (!Number.isInteger(id) || id <= 0) return
    if (!window.confirm(`确定恢复“${version.name}”的第 ${version.version_number} 个卷纲版本吗？`)) return
    setRestoringVersion(version.id)
    try {
      await api.restoreOutlineVolumeVersion(id, version.id)
      setNotice(`已恢复“${version.name}”的第 ${version.version_number} 个卷纲版本`)
      await loadVersions()
    } catch (reason) {
      setNotice(reason instanceof Error ? reason.message : '恢复卷纲版本失败，请稍后重试')
    } finally {
      setRestoringVersion(null)
    }
  }

  async function restoreRollingVersion(version: ChapterVersion) {
    const id = Number(projectId)
    if (!Number.isInteger(id) || id <= 0) return
    if (!window.confirm(`确定恢复“第 ${version.chapter_number} 章 ${version.chaptername || ''}”的细纲版本吗？`)) return
    setRestoringVersion(version.id)
    try {
      await api.restoreRollingOutlineVersion(id, version.id)
      setNotice(`已恢复第 ${version.chapter_number} 章的细纲版本`)
      await loadVersions()
    } catch (reason) {
      setNotice(reason instanceof Error ? reason.message : '恢复细纲版本失败，请稍后重试')
    } finally {
      setRestoringVersion(null)
    }
  }

  function beginEditing() {
    setDraft(outline)
    setNotice('')
    setEditing(true)
  }

  function cancelEditing() {
    setDraft(outline)
    setExpectedWords(savedExpectedWords)
    setEditing(false)
    setNotice('')
  }

  async function saveOutline() {
    const id = Number(projectId)
    const words = Number(expectedWords)
    if (!Number.isInteger(words) || words <= 0 || words > 10000000) {
      setNotice('请输入 1 到 10000000 之间的作品目标字数')
      return
    }
    setSaving(true)
    setNotice('')
    try {
      const saved = await api.updateProjectOutline(id, draft, words)
      setOutline(saved.outline || '')
      setDraft(saved.outline || '')
      setSavedExpectedWords(String(words))
      setEditing(false)
      setNotice('大纲修改已保存')
    } catch (reason) {
      setNotice(reason instanceof Error ? reason.message : '大纲保存失败，请稍后重试')
    } finally {
      setSaving(false)
    }
  }

  async function generateOutline() {
    const id = Number(projectId)
    const words = Number(expectedWords)
    if (!Number.isInteger(words) || words <= 0 || words > 10000000) {
      setGenerationError('请输入 1 到 10000000 之间的期望作品字数')
      return
    }
    setGenerating(true)
    setGenerationError('')
    setDraft('')
    setGenerationDialogOpen(false)
    setNotice('正在生成大纲…')
    const userIdea = generationIdea.trim().slice(0, 3000)
    try {
      const result = await api.generateProjectOutlineStream(
        id,
        words,
        userIdea,
        knowledgeBaseIds,
        inspirationIds,
        chunk => setDraft(current => current + chunk),
      )
      setKnowledgeCitations(result.citations || [])
      setExpectedWords(String(result.expected_words || words))
      setSavedExpectedWords(String(result.expected_words || words))
      setNotice('大纲已生成，请检查后点击“保存修改”入库')
    } catch (reason) {
      setNotice(reason instanceof Error ? reason.message : '大纲生成失败，请稍后重试')
    } finally {
      setGenerating(false)
    }
  }

  function openNewVolumeDialog() {
    const nextNumber = volumes.reduce((max, volume) => Math.max(max, volume.volume_number), 0) + 1
    setNewVolumeDraft({
      volume_number: String(nextNumber),
      name: `第${nextNumber}卷`,
      outline: '',
    })
    setVolumeError('')
    setNewVolumeDialogOpen(true)
  }

  async function addVolume() {
    const id = Number(projectId)
    const volumeNumber = Number(newVolumeDraft.volume_number)
    if (!Number.isInteger(volumeNumber) || volumeNumber <= 0) return setVolumeError('请输入有效的卷序号')
    if (!newVolumeDraft.name.trim()) return setVolumeError('请输入卷名')
    setVolumeSaving(-1)
    setVolumeError('')
    try {
      const created = await api.createOutlineVolume(id, {
        volume_number: volumeNumber,
        name: newVolumeDraft.name.trim(),
        outline: newVolumeDraft.outline.trim(),
      })
      setVolumes(current => [...current, created].sort((left, right) => left.volume_number - right.volume_number))
      setVolumeEditing(current => ({ ...current, [created.id]: true }))
      setNewVolumeDialogOpen(false)
      setNotice('卷纲单元已创建')
    } catch (reason) {
      setVolumeError(reason instanceof Error ? reason.message : '创建卷纲失败，请稍后重试')
    } finally {
      setVolumeSaving(null)
    }
  }

  async function saveVolume(volume: OutlineVolume) {
    setVolumeSaving(volume.id)
    try {
      const saved = await api.updateOutlineVolume(Number(projectId), volume.id, {
        volume_number: volume.volume_number,
        name: volume.name,
        outline: volume.outline,
      })
      const refreshed = await api.getOutlineVolumes(Number(projectId))
      setVolumes(refreshed)
      setVolumeEditing(current => ({ ...current, [saved.id]: false }))
      setNotice(`${saved.name}已保存`)
    } catch (reason) {
      setVolumeError(reason instanceof Error ? reason.message : '卷纲保存失败，请稍后重试')
    } finally {
      setVolumeSaving(null)
    }
  }

  async function generateVolume(volume: OutlineVolume) {
    setVolumeGenerating(volume.id)
    setVolumeError('')
    try {
      const result = await api.generateOutlineVolume(
        Number(projectId),
        volume.id,
        volumeIdeas[volume.id] || '',
        knowledgeBaseIds,
      )
      setVolumes(current => current.map(item => (item.id === volume.id ? { ...item, outline: result.outline } : item)))
      setVolumeEditing(current => ({ ...current, [volume.id]: true }))
      setKnowledgeCitations(result.citations || [])
      setNotice(`${volume.name}已生成，请检查后保存卷纲`)
    } catch (reason) {
      setVolumeError(reason instanceof Error ? reason.message : '卷纲生成失败，请稍后重试')
    } finally {
      setVolumeGenerating(null)
    }
  }

  async function generateVolumePlan() {
    const id = Number(projectId)
    const words = Number(savedExpectedWords)
    if (!Number.isInteger(words) || words <= 0) {
      setVolumeError('请先设置有效的作品目标字数')
      return
    }
    if (volumes.length > 0 && !window.confirm('智能分卷会替换现有所有卷纲及卷名，确定继续吗？')) {
      return
    }
    setVolumePlanGenerating(true)
    setVolumeError('')
    try {
      const result = await api.generateOutlineVolumePlan(id, words, volumes.length > 0, knowledgeBaseIds)
      setVolumes(result.volumes)
      setVolumeEditing(Object.fromEntries(result.volumes.map(volume => [volume.id, false])))
      setKnowledgeCitations(result.citations || [])
      setNotice(`已按故事阶段生成并保存${result.volumes.length}卷卷纲`)
    } catch (reason) {
      setVolumeError(reason instanceof Error ? reason.message : '智能分卷失败，请稍后重试')
    } finally {
      setVolumePlanGenerating(false)
    }
  }

  async function removeVolume(volume: OutlineVolume) {
    if (!window.confirm(`确定删除“${volume.name}”吗？`)) return
    try {
      await api.deleteOutlineVolume(Number(projectId), volume.id)
      setVolumes(current => current.filter(item => item.id !== volume.id))
      setVolumeEditing(current => {
        const next = { ...current }
        delete next[volume.id]
        return next
      })
      setNotice(`${volume.name}已移入回收站`)
    } catch (reason) {
      setVolumeError(reason instanceof Error ? reason.message : '删除卷纲失败，请稍后重试')
    }
  }

  async function planRollingChapters() {
    const id = Number(projectId)
    if (!Number.isInteger(id) || id <= 0 || rollingPlanning) return
    setRollingPlanning(true)
    setRollingPlanProgress('正在查找下一批待规划章节…')
    setVolumeError('')
    try {
      const current = [...chapters].sort((left, right) => left.chapter_number - right.chapter_number)
      const latestChapter = current.at(-1)
      let chapterNumber = latestChapter && !latestChapter.plan
        ? latestChapter.chapter_number
        : (latestChapter?.chapter_number || 0) + 1
      const targetNumbers: number[] = []
      const existingChapterIds: number[] = []

      for (let index = 0; index < 5; index += 1) {
        const chapter = current.find(item => item.chapter_number === chapterNumber)
        targetNumbers.push(chapterNumber)
        if (chapter) existingChapterIds.push(chapter.id)
        chapterNumber += 1
      }

      setRollingPlanProgress('正在一次性生成 5 章细纲，生成成功后才会创建缺失章节…')
      const result = await api.generateRollingChapterPlans(
        id,
        existingChapterIds,
        3000,
        '',
        [],
        targetNumbers,
      )
      const refreshed = await api.getProjectChapters(id)
      setChapters(refreshed.sort((left, right) => left.chapter_number - right.chapter_number))
      if (result.volume_complete) {
        const refreshedVolumes = await api.getOutlineVolumes(id)
        setVolumes(refreshedVolumes)
        setNotice(
          `模型判断当前卷目标已完成，下一批将进入下一卷。${result.volume_completion_note ? `依据：${result.volume_completion_note}` : ''}`,
        )
      } else {
        setNotice(`已完成第 ${targetNumbers[0]}～${targetNumbers.at(-1)} 章的滚动细纲规划`)
      }
    } catch (reason) {
      setChapters(current => [...current].sort((left, right) => left.chapter_number - right.chapter_number))
      setVolumeError(reason instanceof Error ? reason.message : '滚动细纲规划失败，请稍后重试')
    } finally {
      setRollingPlanning(false)
      setRollingPlanProgress('')
    }
  }

  if (loading)
    return (
      <div className="page">
        <div className="project-detail-skeleton" aria-label="正在加载大纲详情">
          <span />
          <span />
          <span />
        </div>
      </div>
    )
  if (error)
    return (
      <div className="page">
        <div className="empty-state">
          <BookOpenText size={32} />
          <h3>{error}</h3>
          <Link className="secondary-button" to={`/projects/${projectId}`}>
            <ArrowLeft size={16} />
            返回作品详情
          </Link>
        </div>
      </div>
    )

  if (feature === 'versions')
    return (
      <div className="page detail-page">
        <div className={sidebarCollapsed ? 'detail-layout detail-layout-collapsed' : 'detail-layout'}>
          <aside className={sidebarCollapsed ? 'detail-sidebar collapsed' : 'detail-sidebar'} aria-label="大纲功能侧栏">
            <Link className="text-link detail-sidebar-back" to={`/projects/${projectId}`}>
              <ArrowLeft size={16} />
              返回作品详情
            </Link>
            <button
              className="icon-button detail-sidebar-collapse"
              type="button"
              onClick={() => setSidebarCollapsed(current => !current)}
              aria-label={sidebarCollapsed ? '展开大纲功能侧栏' : '收起大纲功能侧栏'}
            >
              {sidebarCollapsed ? <PanelLeftOpen size={16} /> : <PanelLeftClose size={16} />}
            </button>
            <p className="detail-sidebar-eyebrow">大纲工具</p>
            <Link
              className={`detail-sidebar-link${feature === 'versions' ? '' : ' active'}`}
              to={`/projects/${projectId}/outline`}
              aria-current={feature === 'versions' ? undefined : 'page'}
            >
              <BookOpenText size={15} />
              大纲详情
            </Link>
            <Link
              className={`detail-sidebar-link${feature === 'versions' ? ' active' : ''}`}
              to={`/projects/${projectId}/outline/versions`}
              aria-current={feature === 'versions' ? 'page' : undefined}
            >
              <RotateCcw size={15} />
              大纲版本
            </Link>
          </aside>
          <div className="detail-main">
            <section className="content-section detail-subpage-panel">
              <p className="eyebrow">版本管理</p>
              <h1>大纲版本</h1>
              <p className="outline-help">{projectName} · 按总纲、卷纲和滚动细纲查看历史快照。</p>
              <div className="outline-level-tabs" role="tablist" aria-label="大纲版本类型">
                {([
                  ['total', '总纲'],
                  ['volumes', '卷纲'],
                  ['chapters', '滚动细纲'],
                ] as const).map(([key, label]) => (
                  <button
                    className={versionTab === key ? 'outline-level-tab active' : 'outline-level-tab'}
                    type="button"
                    role="tab"
                    id={`outline-version-${key}-tab`}
                    aria-selected={versionTab === key}
                    aria-controls="outline-version-content"
                    key={key}
                    onClick={() => setVersionTab(key)}
                  >
                    {label}
                  </button>
                ))}
              </div>
              <section
                id="outline-version-content"
                className="generation-history-panel outline-version-panel"
                role="tabpanel"
                aria-labelledby={`outline-version-${versionTab}-tab`}
              >
                {versionsLoading && <p className="chapter-placeholder">正在加载版本历史…</p>}
                {!versionsLoading && versionTab === 'total' && versions.length === 0 && (
                  <p className="chapter-placeholder">保存总纲后会在这里留下版本快照。</p>
                )}
                {!versionsLoading && versionTab === 'total' && versions.map(version => (
                    <article className="generation-history-item" key={version.id}>
                      <div className="generation-history-copy">
                        <strong>版本 {version.version_number}</strong>
                        <small>
                          {new Date(version.created_at).toLocaleString()} ·{' '}
                          {version.source === 'before_restore' ? '恢复前自动保存' : '保存前自动保存'}
                        </small>
                        <p>{version.outline ? `${version.outline.length} 字` : '暂无内容'}</p>
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
                {!versionsLoading && versionTab === 'volumes' && volumeVersions.length === 0 && (
                  <p className="chapter-placeholder">修改、删除或重新生成卷纲后，会在这里留下版本快照。</p>
                )}
                {!versionsLoading && versionTab === 'volumes' && volumeVersions.map(version => (
                  <article className="generation-history-item" key={version.id}>
                    <div className="generation-history-copy">
                      <strong>{version.name} · 版本 {version.version_number}</strong>
                      <small>{new Date(version.created_at).toLocaleString()} · {version.source === 'before_restore' ? '恢复前自动保存' : version.source === 'before_regenerate' ? '重新生成前自动保存' : '修改前自动保存'}</small>
                      <p>{version.outline ? `${version.outline.length} 字卷纲` : '暂无卷纲内容'}</p>
                      {version.outline && <p>{version.outline}</p>}
                    </div>
                    <div className="generation-history-actions">
                      <button className="secondary-button" type="button" onClick={() => void restoreVolumeVersion(version)} disabled={restoringVersion !== null}>
                        {restoringVersion === version.id ? '正在恢复…' : '恢复此版本'}
                      </button>
                    </div>
                  </article>
                ))}
                {!versionsLoading && versionTab === 'chapters' && rollingVersions.length === 0 && (
                  <p className="chapter-placeholder">修改章节细纲后，会在这里留下版本快照。</p>
                )}
                {!versionsLoading && versionTab === 'chapters' && rollingVersions.map(version => (
                  <article className="generation-history-item" key={version.id}>
                    <div className="generation-history-copy">
                      <strong>第 {version.chapter_number} 章 · {version.chaptername || '未命名章节'} · 版本 {version.version_number}</strong>
                      <small>{new Date(version.created_at).toLocaleString()} · {version.source === 'before_plan_restore' ? '恢复细纲前自动保存' : version.source === 'before_restore' ? '恢复章节前自动保存' : '修改前自动保存'}</small>
                      <p>{version.plan?.objective || '暂无本章目标'}</p>
                      {version.plan?.key_events && <p>{version.plan.key_events}</p>}
                      {version.plan?.ending_hook && <p>结尾钩子：{version.plan.ending_hook}</p>}
                    </div>
                    <div className="generation-history-actions">
                      <button className="secondary-button" type="button" onClick={() => void restoreRollingVersion(version)} disabled={restoringVersion !== null}>
                        {restoringVersion === version.id ? '正在恢复…' : '恢复此版本'}
                      </button>
                    </div>
                  </article>
                ))}
              </section>
            </section>
          </div>
        </div>
      </div>
    )

  return (
    <div className="page detail-page">
      <div className={sidebarCollapsed ? 'detail-layout detail-layout-collapsed' : 'detail-layout'}>
        <aside className={sidebarCollapsed ? 'detail-sidebar collapsed' : 'detail-sidebar'} aria-label="大纲功能侧栏">
          <Link className="text-link detail-sidebar-back" to={`/projects/${projectId}`}>
            <ArrowLeft size={16} />
            返回作品详情
          </Link>
          <button
            className="icon-button detail-sidebar-collapse"
            type="button"
            onClick={() => setSidebarCollapsed(current => !current)}
            aria-label={sidebarCollapsed ? '展开大纲功能侧栏' : '收起大纲功能侧栏'}
            title={sidebarCollapsed ? '展开大纲功能侧栏' : '收起大纲功能侧栏'}
          >
            {sidebarCollapsed ? <PanelLeftOpen size={16} /> : <PanelLeftClose size={16} />}
          </button>
          <p className="detail-sidebar-eyebrow">大纲工具</p>
          <Link
            className={`detail-sidebar-link${feature === 'versions' ? '' : ' active'}`}
            to={`/projects/${projectId}/outline`}
            aria-current={feature === 'versions' ? undefined : 'page'}
          >
            <BookOpenText size={15} />
            大纲详情
          </Link>
          <Link
            className={`detail-sidebar-link${feature === 'versions' ? ' active' : ''}`}
            to={`/projects/${projectId}/outline/versions`}
            aria-current={feature === 'versions' ? 'page' : undefined}
          >
            <RotateCcw size={15} />
            大纲版本
          </Link>
        </aside>
        <div className="detail-main">
          {notice && (
            <div className="form-message success page-notice" role="status">
              {notice}
            </div>
          )}
          <div className="detail-page-toolbar">
            {editing && activeLevel === 'total' ? (
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
                  onClick={() => void saveOutline()}
                  disabled={saving || generating}
                >
                  <Save size={15} />
                  {saving ? '正在保存…' : '保存修改'}
                </button>
              </>
            ) : activeLevel === 'total' ? (
              <button className="primary-button" type="button" onClick={beginEditing}>
                <Edit3 size={15} />
                编辑总纲
              </button>
            ) : null}
          </div>
          <section className="content-section outline-detail-panel">
            <p className="eyebrow">大纲详情</p>
            <div className="outline-title-row">
              <h1>{projectName}</h1>
              {editing && activeLevel === 'total' ? (
                <label className="outline-target-words">
                  <span>目标字数</span>
                  <input
                    type="number"
                    min="1"
                    max="10000000"
                    value={expectedWords}
                    onChange={event => setExpectedWords(event.target.value)}
                    aria-label="作品目标字数"
                    disabled={generating || saving}
                  />
                  <span>字</span>
                </label>
              ) : (
                <span className="outline-target-words-display">
                  目标字数：{Number(expectedWords).toLocaleString()} 字
                </span>
              )}
            </div>
            <p className="outline-help">梳理故事主线、人物关系和关键情节点，让创作始终有清晰方向。</p>
            <div className="outline-level-tabs" role="tablist" aria-label="大纲层级">
              {(
                [
                  ['total', '总纲'],
                  ['volumes', '卷纲'],
                  ['chapters', '滚动细纲'],
                ] as const
              ).map(([level, label]) => (
                <button
                  className={activeLevel === level ? 'outline-level-tab active' : 'outline-level-tab'}
                  type="button"
                  role="tab"
                  aria-selected={activeLevel === level}
                  key={level}
                  onClick={() => {
                    if (editing && level !== 'total') cancelEditing()
                    setActiveLevel(level)
                  }}
                >
                  {label}
                </button>
              ))}
            </div>
            {activeLevel === 'total' && editing ? (
              <div className="outline-editor-field">
                <div className="editor-field-heading">
                  <span>作品大纲</span>
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
                    智能生成
                  </button>
                </div>
                <textarea
                  value={draft}
                  onChange={event => setDraft(event.target.value)}
                  rows={24}
                  maxLength={100000}
                  aria-label="作品大纲"
                  placeholder="在这里写下作品大纲…"
                  disabled={generating || saving}
                />
                <div className="outline-word-count" aria-live="polite">
                  大纲字数：{draft.length}
                </div>
              </div>
            ) : activeLevel === 'total' ? (
              <>
                <div className="outline-content-view">{outline || '暂未填写大纲，点击右上方“编辑大纲”开始编写。'}</div>
                <div className="outline-word-count">大纲字数：{outline.length}</div>
              </>
            ) : activeLevel === 'volumes' ? (
              <div className="outline-volume-section">
                <div className="editor-field-heading">
                  <span>卷纲 · 建议按阶段里程碑规划，每卷明确核心事件与卷末钩子</span>
                  <button
                    className="secondary-button"
                    type="button"
                    onClick={() => void generateVolumePlan()}
                    disabled={
                      volumeLoading || volumePlanGenerating || volumeGenerating !== null || volumeSaving !== null
                    }
                  >
                    <Sparkles size={15} />
                    {volumePlanGenerating ? '正在智能分卷…' : '智能分卷'}
                  </button>
                  <button
                    className="secondary-button"
                    type="button"
                    onClick={openNewVolumeDialog}
                    disabled={volumeLoading || volumePlanGenerating || volumeSaving !== null}
                  >
                    <BookOpenText size={15} />
                    新建卷纲
                  </button>
                </div>
                {volumeError && (
                  <p className="form-message error" role="alert">
                    {volumeError}
                  </p>
                )}
                {volumeLoading ? <p className="chapter-placeholder">正在加载卷纲…</p> : null}
                {volumePlanGenerating && (
                  <p className="chapter-placeholder">正在结合全书总纲和目标字数生成分卷方案及卷纲…</p>
                )}
                {!volumeLoading && volumes.length === 0 && (
                  <p className="chapter-placeholder">先创建卷纲单元，再填写本卷核心事件、人物变化和收尾钩子。</p>
                )}
                {volumes.map(volume => (
                  <article className="outline-volume-card" key={volume.id}>
                    <div className="outline-volume-heading">
                      <h2>{volume.name}</h2>
                      <small className="outline-help">
                        {volume.is_completed
                          ? '本卷目标已完成'
                          : volumes.find(item => !item.is_completed)?.id === volume.id
                            ? '当前推进卷'
                            : '等待进入'}
                        {volume.completion_note ? ` · ${volume.completion_note}` : ''}
                      </small>
                      <div className="outline-volume-actions">
                        {!volumeEditing[volume.id] && (
                          <button
                            className="secondary-button"
                            type="button"
                            onClick={() => setVolumeEditing(current => ({ ...current, [volume.id]: true }))}
                            disabled={volumeGenerating !== null || volumeSaving !== null || volumePlanGenerating}
                          >
                            <Edit3 size={14} />
                            修改卷纲
                          </button>
                        )}
                        {volumeEditing[volume.id] && (
                          <button
                            className="secondary-button"
                            type="button"
                            onClick={() => void generateVolume(volume)}
                            disabled={volumeGenerating !== null || volumeSaving !== null || volumePlanGenerating}
                          >
                            <Sparkles size={14} />
                            {volumeGenerating === volume.id ? '生成中…' : '智能生成卷纲'}
                          </button>
                        )}
                        {volumeEditing[volume.id] && (
                          <button
                            className="secondary-button"
                            type="button"
                            onClick={() => void saveVolume(volume)}
                            disabled={volumeSaving !== null}
                          >
                            <Save size={14} />
                            {volumeSaving === volume.id ? '保存中…' : '保存卷纲'}
                          </button>
                        )}
                      </div>
                    </div>
                    <label className="detail-edit-field">
                      <span>本卷补充想法（选填）</span>
                      <textarea
                        rows={2}
                        maxLength={5000}
                        value={volumeIdeas[volume.id] || ''}
                        onChange={event => setVolumeIdeas(current => ({ ...current, [volume.id]: event.target.value }))}
                        aria-label={`${volume.name}补充想法`}
                        placeholder="补充本卷想重点呈现的冲突、人物变化或伏笔…"
                        disabled={!volumeEditing[volume.id]}
                      />
                    </label>
                    <div className="outline-volume-fields">
                      <label className="detail-edit-field">
                        <span>卷序号</span>
                        <input
                          type="number"
                          min="1"
                          value={volume.volume_number}
                          onChange={event =>
                            setVolumes(current =>
                              current.map(item =>
                                item.id === volume.id
                                  ? { ...item, volume_number: Number(event.target.value) || 1 }
                                  : item,
                              ),
                            )
                          }
                          aria-label={`${volume.name}卷序号`}
                          disabled={!volumeEditing[volume.id]}
                        />
                      </label>
                      <label className="detail-edit-field">
                        <span>卷名</span>
                        <input
                          value={volume.name}
                          onChange={event =>
                            setVolumes(current =>
                              current.map(item =>
                                item.id === volume.id ? { ...item, name: event.target.value } : item,
                              ),
                            )
                          }
                          aria-label={`${volume.name}卷名`}
                          disabled={!volumeEditing[volume.id]}
                        />
                      </label>
                    </div>
                    <label className="detail-edit-field">
                      <span>阶段目标、核心事件、人物变化与卷末钩子</span>
                      <textarea
                        rows={7}
                        value={volume.outline || ''}
                        onChange={event =>
                          setVolumes(current =>
                            current.map(item =>
                              item.id === volume.id ? { ...item, outline: event.target.value } : item,
                            ),
                          )
                        }
                        aria-label={`${volume.name}卷纲`}
                        placeholder="描述本卷的阶段目标、主要冲突、人物状态变化和卷末钩子…"
                        disabled={!volumeEditing[volume.id]}
                      />
                    </label>
                    <div className="outline-volume-footer">
                      <div className="outline-word-count">卷纲字数：{(volume.outline || '').length}</div>
                      {volumeEditing[volume.id] && (
                        <button
                          className="secondary-button danger-button outline-volume-delete"
                          type="button"
                          onClick={() => void removeVolume(volume)}
                        >
                          <Trash2 size={14} />
                          删除
                        </button>
                      )}
                    </div>
                  </article>
                ))}
              </div>
            ) : (
              <div className="outline-chapter-list">
                <div className="editor-field-heading">
                  <p className="outline-help">按当前卷纲规划接下来5章；系统判断本卷目标完成后，下一批自动使用下一卷卷纲。</p>
                  <button
                    className="secondary-button"
                    type="button"
                    onClick={() => void planRollingChapters()}
                    disabled={rollingPlanning || volumeLoading || volumePlanGenerating}
                    aria-label="智能规划滚动细纲"
                  >
                    <Sparkles size={15} />
                    {rollingPlanning ? '正在规划…' : '智能规划'}
                  </button>
                </div>
                {volumeError && (
                  <p className="form-message error" role="alert">
                    {volumeError}
                  </p>
                )}
                {rollingPlanProgress && <p className="chapter-placeholder">{rollingPlanProgress}</p>}
                {volumeLoading ? <p className="chapter-placeholder">正在加载章节细纲…</p> : null}
                {!volumeLoading && rollingChapters.length === 0 && (
                  <p className="chapter-placeholder">
                    当前章节均已有细纲。点击“智能规划”可自动新增并规划下一批5章。
                  </p>
                )}
                {rollingChapters.map(item => (
                  <Link className="outline-chapter-row" to={`/projects/${projectId}/chapters/${item.id}`} key={item.id}>
                    <span className="outline-chapter-number">第{item.chapter_number}章</span>
                    <span className="outline-chapter-copy">
                      <strong>{item.chaptername || `第${item.chapter_number}章`}</strong>
                      <small>{item.plan?.objective || '尚未填写细纲'}</small>
                    </span>
                    <span className="outline-chapter-count">
                      {item.plan
                        ? `${item.plan.objective.length + item.plan.conflict.length + item.plan.key_events.length + item.plan.ending_hook.length}字细纲`
                        : '去规划'}
                    </span>
                  </Link>
                ))}
              </div>
            )}
          </section>
          <KnowledgeCitationList citations={knowledgeCitations} />
        </div>
      </div>
      {newVolumeDialogOpen && (
        <div className="modal-backdrop" role="presentation" onMouseDown={event => {
          if (event.target === event.currentTarget && volumeSaving === null) setNewVolumeDialogOpen(false)
        }}>
          <section className="modal generation-modal" role="dialog" aria-modal="true" aria-labelledby="new-volume-title">
            <div className="modal-header">
              <h2 id="new-volume-title">新建卷纲</h2>
              <button
                className="icon-button"
                type="button"
                onClick={() => setNewVolumeDialogOpen(false)}
                aria-label="关闭新建卷纲弹窗"
                disabled={volumeSaving !== null}
              >
                <X size={18} />
              </button>
            </div>
            <div className="modal-body generation-modal-body">
              <div className="outline-volume-fields">
                <label className="detail-edit-field">
                  <span>卷序号</span>
                  <input
                    type="number"
                    min="1"
                    value={newVolumeDraft.volume_number}
                    onChange={event => setNewVolumeDraft(current => ({ ...current, volume_number: event.target.value }))}
                    aria-label="新卷序号"
                  />
                </label>
                <label className="detail-edit-field">
                  <span>卷名</span>
                  <input
                    value={newVolumeDraft.name}
                    onChange={event => setNewVolumeDraft(current => ({ ...current, name: event.target.value }))}
                    maxLength={100}
                    aria-label="新卷名"
                  />
                </label>
              </div>
              <label className="detail-edit-field">
                <span>卷纲（选填）</span>
                <textarea
                  rows={6}
                  value={newVolumeDraft.outline}
                  onChange={event => setNewVolumeDraft(current => ({ ...current, outline: event.target.value }))}
                  maxLength={100000}
                  aria-label="新卷卷纲"
                  placeholder="可以先填写卷纲，也可以创建后再编辑。"
                />
              </label>
              {volumeError && <p className="form-message error" role="alert">{volumeError}</p>}
              <div className="modal-actions">
                <button className="secondary-button" type="button" onClick={() => setNewVolumeDialogOpen(false)} disabled={volumeSaving !== null}>取消</button>
                <button className="primary-button" type="button" onClick={() => void addVolume()} disabled={volumeSaving !== null}>
                  {volumeSaving === -1 ? '创建中…' : '确认创建'}
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
            aria-labelledby="outline-generation-title"
          >
            <div className="modal-header">
              <h2 id="outline-generation-title">智能生成作品大纲</h2>
              <button
                className="icon-button"
                type="button"
                onClick={() => setGenerationDialogOpen(false)}
                aria-label="关闭大纲生成弹窗"
                disabled={generating}
              >
                <X size={18} />
              </button>
            </div>
            <div className="modal-body generation-modal-body">
              <label className="detail-edit-field">
                <span>作品目标总字数（用于规划）</span>
                <input
                  type="number"
                  min="1"
                  max="10000000"
                  value={expectedWords}
                  onChange={event => setExpectedWords(event.target.value)}
                  aria-label="大纲生成期望字数"
                />
                <small className="field-help">仅用于安排分卷和情节体量，不会生成同等字数的大纲。</small>
              </label>
              <InspirationSelector
                selectedIds={inspirationIds}
                onChange={setInspirationIds}
                onItemsChange={setInspirationItems}
              />
              <KnowledgeBaseSelector selectedIds={knowledgeBaseIds} onChange={setKnowledgeBaseIds} />
              <label className="detail-edit-field">
                <span>你的想法（选填）</span>
                <textarea
                  value={generationIdea}
                  onChange={event => setGenerationIdea(event.target.value)}
                  rows={5}
                  maxLength={3000}
                  aria-label="大纲生成想法"
                  placeholder="例如：希望采用双主角视角，故事中段出现身份反转，结局温暖但留有余韵。"
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
                  onClick={() => setGenerationDialogOpen(false)}
                  disabled={generating}
                >
                  取消
                </button>
                <button
                  className="primary-button"
                  type="button"
                  onClick={() => void generateOutline()}
                  disabled={generating}
                >
                  <Sparkles size={15} />
                  {generating ? '正在生成…' : '生成大纲'}
                </button>
              </div>
            </div>
          </section>
        </div>
      )}
    </div>
  )
}
