import {
  ArrowLeft,
  BookOpenText,
  Edit3,
  PanelLeftClose,
  PanelLeftOpen,
  RotateCcw,
  Save,
  Sparkles,
  X,
} from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../api/client'
import type { KnowledgeCitation, OutlineVersion } from '../types'
import { KnowledgeBaseSelector } from '../components/KnowledgeBaseSelector'
import { KnowledgeCitationList } from '../components/KnowledgeCitationList'

export function OutlineDetailPage() {
  const { projectId, feature } = useParams()
  const [outline, setOutline] = useState('')
  const [draft, setDraft] = useState('')
  const [projectName, setProjectName] = useState('作品大纲')
  const [editing, setEditing] = useState(false)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [expectedWords, setExpectedWords] = useState('100000')
  const [generationIdea, setGenerationIdea] = useState('')
  const [generationDialogOpen, setGenerationDialogOpen] = useState(false)
  const [generationError, setGenerationError] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [versions, setVersions] = useState<OutlineVersion[]>([])
  const [versionsOpen, setVersionsOpen] = useState(false)
  const [versionsLoading, setVersionsLoading] = useState(false)
  const [restoringVersion, setRestoringVersion] = useState<number | null>(null)
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const [knowledgeBaseIds, setKnowledgeBaseIds] = useState<number[]>([])
  const [knowledgeCitations, setKnowledgeCitations] = useState<KnowledgeCitation[]>([])

  const loadOutline = useCallback(async () => {
    const id = Number(projectId)
    if (!Number.isInteger(id) || id <= 0) throw new Error('作品编号无效')
    const [value, project] = await Promise.all([api.getProjectOutline(id), api.getProject(id)])
    setOutline(value.outline || '')
    setDraft(value.outline || '')
    setProjectName(project.projectname || '作品大纲')
    setExpectedWords(String(project.expected_words || 100000))
  }, [projectId])

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
    const getVersions = (api as typeof api & { getOutlineVersions?: (projectId: number) => Promise<OutlineVersion[]> })
      .getOutlineVersions
    if (!Number.isInteger(id) || id <= 0 || typeof getVersions !== 'function') return
    setVersionsLoading(true)
    try {
      setVersions(await getVersions(id))
    } catch {
      setNotice('大纲版本历史暂时无法加载')
    } finally {
      setVersionsLoading(false)
    }
  }, [projectId])

  useEffect(() => {
    if (versionsOpen) void loadVersions()
  }, [versionsOpen, loadVersions])

  async function restoreVersion(version: OutlineVersion) {
    const id = Number(projectId)
    const restore = (
      api as typeof api & {
        restoreOutlineVersion?: (projectId: number, versionId: number) => Promise<{ outline: string | null }>
      }
    ).restoreOutlineVersion
    if (!Number.isInteger(id) || typeof restore !== 'function') return
    if (!window.confirm(`确定恢复到第 ${version.version_number} 个版本吗？当前大纲会自动保存为新版本。`)) return
    setRestoringVersion(version.id)
    try {
      const restored = await restore(id, version.id)
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

  function beginEditing() {
    setDraft(outline)
    setNotice('')
    setEditing(true)
  }

  function cancelEditing() {
    setDraft(outline)
    setEditing(false)
    setNotice('')
  }

  async function saveOutline() {
    const id = Number(projectId)
    setSaving(true)
    setNotice('')
    try {
      const saved = await api.updateProjectOutline(id, draft)
      setOutline(saved.outline || '')
      setDraft(saved.outline || '')
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
    try {
      const result = knowledgeBaseIds.length
        ? await api.generateProjectOutline(id, words, generationIdea, knowledgeBaseIds)
        : await api.generateProjectOutline(id, words, generationIdea)
      setDraft(result.outline)
      setKnowledgeCitations(result.citations || [])
      setGenerationDialogOpen(false)
      setNotice('大纲已生成，请检查后点击“保存修改”入库')
    } catch (reason) {
      setGenerationError(reason instanceof Error ? reason.message : '大纲生成失败，请稍后重试')
    } finally {
      setGenerating(false)
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
            <Link className="detail-sidebar-link detail-sidebar-detail-link" to={`/projects/${projectId}/outline`}>
              <BookOpenText size={15} />
              大纲详情
            </Link>
            <Link className="detail-sidebar-link" to={`/projects/${projectId}/outline/versions`}>
              <RotateCcw size={15} />
              大纲版本
            </Link>
          </aside>
          <div className="detail-main">
            <section className="content-section detail-subpage-panel">
              <p className="eyebrow">版本管理</p>
              <h1>大纲版本</h1>
              <p className="outline-help">{projectName} · 每次保存前会自动创建快照。</p>
              <section className="generation-history-panel outline-version-panel">
                {versionsLoading && <p className="chapter-placeholder">正在加载版本历史…</p>}
                {!versionsLoading && versions.length === 0 && (
                  <p className="chapter-placeholder">保存大纲后会在这里留下版本快照。</p>
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
          <Link className="detail-sidebar-link detail-sidebar-detail-link" to={`/projects/${projectId}/outline`}>
            <BookOpenText size={15} />
            大纲详情
          </Link>
          <Link className="detail-sidebar-link" to={`/projects/${projectId}/outline/versions`}>
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
                  onClick={() => void saveOutline()}
                  disabled={saving || generating}
                >
                  <Save size={15} />
                  {saving ? '正在保存…' : '保存修改'}
                </button>
              </>
            ) : (
              <button className="primary-button" type="button" onClick={beginEditing}>
                <Edit3 size={15} />
                编辑大纲
              </button>
            )}
          </div>
          <section className="content-section outline-detail-panel">
            <p className="eyebrow">大纲详情</p>
            <h1>{projectName}</h1>
            <p className="outline-help">梳理故事主线、人物关系和关键情节点，让创作始终有清晰方向。</p>
            {editing ? (
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
                />
              </div>
            ) : (
              <div className="outline-content-view">{outline || '暂未填写大纲，点击左侧“编辑大纲”开始编写。'}</div>
            )}
          </section>
          <KnowledgeCitationList citations={knowledgeCitations} />
        </div>
      </div>
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
              <KnowledgeBaseSelector selectedIds={knowledgeBaseIds} onChange={setKnowledgeBaseIds} />
              <label className="detail-edit-field">
                <span>你的想法（选填）</span>
                <textarea
                  value={generationIdea}
                  onChange={event => setGenerationIdea(event.target.value)}
                  rows={5}
                  maxLength={5000}
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
