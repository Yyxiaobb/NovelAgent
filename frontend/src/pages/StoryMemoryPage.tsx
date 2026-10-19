import { ArrowLeft, BookOpenText, Check, Plus, Save, Trash2, X } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../api/client'
import type {
  Chapter,
  Project,
  StoryMemoryCategory,
  StoryMemoryConflict,
  StoryMemoryEntry,
  StoryMemoryPayload,
} from '../types'

const categories: Array<{ value: StoryMemoryCategory; label: string }> = [
  { value: 'character', label: '人物档案' },
  { value: 'world', label: '世界设定' },
  { value: 'thread', label: '未解线索' },
  { value: 'timeline', label: '时间线' },
]

const emptyDraft = (): StoryMemoryPayload => ({
  category: 'character',
  title: '',
  content: '',
  keywords: [],
  source_chapter_id: null,
  is_active: true,
})

export function StoryMemoryPage() {
  const { projectId } = useParams()
  const id = Number(projectId)
  const [project, setProject] = useState<Project | null>(null)
  const [entries, setEntries] = useState<StoryMemoryEntry[]>([])
  const [conflicts, setConflicts] = useState<StoryMemoryConflict[]>([])
  const [selectedIds, setSelectedIds] = useState<number[]>([])
  const [chapters, setChapters] = useState<Chapter[]>([])
  const [draft, setDraft] = useState<StoryMemoryPayload>(emptyDraft())
  const [keywordText, setKeywordText] = useState('')
  const [editingId, setEditingId] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const load = useCallback(async () => {
    if (!Number.isInteger(id) || id <= 0) {
      setError('作品编号无效')
      setLoading(false)
      return
    }
    setLoading(true)
    setError('')
    try {
      const [detail, memories, chapterList, conflictList] = await Promise.all([
        api.getProject(id),
        api.getProjectMemories(id),
        api.getProjectChapters(id),
        api.getProjectMemoryConflicts(id),
      ])
      setProject(detail)
      setEntries(memories)
      setChapters(chapterList)
      setConflicts(conflictList)
      setSelectedIds([])
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '长期记忆加载失败')
    } finally {
      setLoading(false)
    }
  }, [id])

  useEffect(() => {
    void load()
  }, [load])

  function beginEdit(entry: StoryMemoryEntry) {
    setEditingId(entry.id)
    setDraft({
      category: entry.category,
      title: entry.title,
      content: entry.content,
      keywords: entry.keywords || [],
      source_chapter_id: entry.source_chapter_id,
      is_active: entry.is_active,
    })
    setKeywordText((entry.keywords || []).join('，'))
    setNotice('')
  }

  function resetDraft() {
    setEditingId(null)
    setDraft(emptyDraft())
    setKeywordText('')
  }

  async function save() {
    const title = draft.title.trim()
    const content = draft.content.trim()
    if (!title || !content) {
      setNotice('请填写记忆名称和内容')
      return
    }
    setSaving(true)
    setNotice('')
    const payload = {
      ...draft,
      title,
      content,
      keywords: keywordText
        .split(/[,，、\n]/)
        .map(item => item.trim())
        .filter(Boolean)
        .slice(0, 30),
    }
    try {
      const saved = editingId
        ? await api.updateProjectMemory(id, editingId, payload)
        : await api.createProjectMemory(id, payload)
      setEntries(current => {
        const next = editingId ? current.map(item => (item.id === saved.id ? saved : item)) : [...current, saved]
        return next.sort(
          (left, right) => left.category.localeCompare(right.category) || left.title.localeCompare(right.title),
        )
      })
      resetDraft()
      setNotice(editingId ? '长期记忆已更新' : '长期记忆已添加')
    } catch (reason) {
      setNotice(reason instanceof Error ? reason.message : '保存失败，请稍后重试')
    } finally {
      setSaving(false)
    }
  }

  async function remove(entry: StoryMemoryEntry) {
    if (!window.confirm(`确定删除“${entry.title}”这条长期记忆吗？`)) return
    try {
      await api.deleteProjectMemory(id, entry.id)
      setEntries(current => current.filter(item => item.id !== entry.id))
      if (editingId === entry.id) resetDraft()
      setNotice('长期记忆已删除')
    } catch (reason) {
      setNotice(reason instanceof Error ? reason.message : '删除失败，请稍后重试')
    }
  }

  async function review(entry: StoryMemoryEntry, decision: 'approved' | 'rejected') {
    try {
      const updated = await api.reviewProjectMemory(id, entry.id, decision)
      setEntries(current => current.map(item => (item.id === updated.id ? updated : item)))
      setNotice(decision === 'approved' ? '记忆已审核并加入后续生成上下文' : '已拒绝该记忆建议')
    } catch (reason) {
      setNotice(reason instanceof Error ? reason.message : '审核失败，请稍后重试')
    }
  }

  const pendingEntries = entries.filter(entry => entry.review_status === 'pending')

  function toggleSelected(memoryId: number) {
    setSelectedIds(current =>
      current.includes(memoryId) ? current.filter(idValue => idValue !== memoryId) : [...current, memoryId],
    )
  }

  async function batchReview(decision: 'approved' | 'rejected') {
    if (selectedIds.length === 0) return
    try {
      const reviewed = await api.batchReviewProjectMemories(id, selectedIds, decision)
      const reviewedById = new Map(reviewed.map(item => [item.id, item]))
      setEntries(current => current.map(item => reviewedById.get(item.id) || item))
      setSelectedIds([])
      setNotice(decision === 'approved' ? `已通过 ${reviewed.length} 条记忆` : `已拒绝 ${reviewed.length} 条记忆`)
    } catch (reason) {
      setNotice(reason instanceof Error ? reason.message : '批量审核失败，请稍后重试')
    }
  }

  if (loading)
    return (
      <div className="page">
        <div className="project-detail-skeleton" aria-label="正在加载长期记忆">
          <span />
          <span />
        </div>
      </div>
    )

  return (
    <div className="page">
      <div className="detail-back-row">
        <Link className="text-link" to={`/projects/${id}`}>
          <ArrowLeft size={16} />
          返回作品详情
        </Link>
      </div>
      <header className="page-header">
        <div>
          <p className="eyebrow">{project?.projectname || '作品'} · 创作资料</p>
          <h1>长期记忆</h1>
          <p>整理人物、世界设定、未解线索和时间线。章节摘要会生成待审核建议，审核通过后才加入生成上下文。</p>
        </div>
      </header>
      {error && (
        <div className="form-message error" role="alert">
          {error}
        </div>
      )}
      {notice && (
        <div className="form-message success" role="status">
          {notice}
        </div>
      )}

      <section className="content-section story-memory-editor">
        <div className="section-heading">
          <div>
            <h2>{editingId ? '编辑记忆' : '添加记忆'}</h2>
            <p>使用具体、稳定的事实；关键词帮助系统在章节规划中找到相关条目。</p>
          </div>
        </div>
        <div className="story-memory-form">
          <label className="detail-edit-field">
            <span>记忆类型</span>
            <select
              value={draft.category}
              onChange={event =>
                setDraft(current => ({ ...current, category: event.target.value as StoryMemoryCategory }))
              }
            >
              {categories.map(category => (
                <option key={category.value} value={category.value}>
                  {category.label}
                </option>
              ))}
            </select>
          </label>
          <label className="detail-edit-field">
            <span>名称</span>
            <input
              value={draft.title}
              maxLength={100}
              onChange={event => setDraft(current => ({ ...current, title: event.target.value }))}
              placeholder="例如：沈砚、北境关隘、失踪的密函"
            />
          </label>
          <label className="detail-edit-field story-memory-wide">
            <span>内容</span>
            <textarea
              value={draft.content}
              maxLength={10000}
              rows={4}
              onChange={event => setDraft(current => ({ ...current, content: event.target.value }))}
              placeholder="记录需要后续章节持续遵守或回收的信息。"
            />
          </label>
          <label className="detail-edit-field">
            <span>检索关键词</span>
            <input
              value={keywordText}
              onChange={event => setKeywordText(event.target.value)}
              placeholder="逗号分隔，例如：北境，地图，信使"
            />
          </label>
          <label className="detail-edit-field">
            <span>来源章节（可选）</span>
            <select
              value={draft.source_chapter_id ?? ''}
              onChange={event =>
                setDraft(current => ({
                  ...current,
                  source_chapter_id: event.target.value ? Number(event.target.value) : null,
                }))
              }
            >
              <option value="">不关联章节</option>
              {chapters.map(chapter => (
                <option key={chapter.id} value={chapter.id}>
                  第 {chapter.chapter_number} 章 · {chapter.chaptername || '未命名章节'}
                </option>
              ))}
            </select>
          </label>
          <label className="story-memory-active">
            <input
              type="checkbox"
              checked={draft.is_active}
              onChange={event => setDraft(current => ({ ...current, is_active: event.target.checked }))}
            />
            <span>用于后续章节生成</span>
          </label>
        </div>
        <div className="section-heading-actions story-memory-actions">
          {editingId && (
            <button className="secondary-button" type="button" onClick={resetDraft} disabled={saving}>
              <X size={15} />
              取消编辑
            </button>
          )}
          <button className="primary-button" type="button" onClick={() => void save()} disabled={saving}>
            <Save size={15} />
            {saving ? (
              '正在保存…'
            ) : editingId ? (
              '保存记忆'
            ) : (
              <>
                <Plus size={15} />
                添加记忆
              </>
            )}
          </button>
        </div>
      </section>

      <section className="content-section story-memory-list">
        <div className="section-heading">
          <div>
            <h2>已整理的记忆</h2>
            <p>{entries.length} 条资料 · 停用的条目不会进入生成上下文</p>
          </div>
          {pendingEntries.length > 0 && (
            <div className="story-memory-batch-actions">
              <button
                className="text-link"
                type="button"
                onClick={() =>
                  setSelectedIds(
                    selectedIds.length === pendingEntries.length ? [] : pendingEntries.map(item => item.id),
                  )
                }
              >
                {selectedIds.length === pendingEntries.length ? '取消全选' : `全选待审核（${pendingEntries.length}）`}
              </button>
              <button
                className="secondary-button"
                type="button"
                onClick={() => void batchReview('rejected')}
                disabled={selectedIds.length === 0}
              >
                批量拒绝
              </button>
              <button
                className="primary-button"
                type="button"
                onClick={() => void batchReview('approved')}
                disabled={selectedIds.length === 0}
              >
                批量通过
              </button>
            </div>
          )}
        </div>
        {conflicts.length > 0 && (
          <div className="story-memory-conflicts" role="status">
            <strong>发现 {conflicts.length} 组可能重复或冲突的记忆</strong>
            {conflicts.slice(0, 8).map(conflict => {
              const first = entries.find(entry => entry.id === conflict.first_id)
              const second = entries.find(entry => entry.id === conflict.second_id)
              return (
                <p key={`${conflict.first_id}-${conflict.second_id}`}>
                  {first?.title || conflict.first_id} ↔ {second?.title || conflict.second_id} ·{' '}
                  {conflict.reason === 'same_title'
                    ? '名称相同'
                    : conflict.reason === 'shared_keywords'
                      ? '关键词重叠'
                      : '内容相似'}
                </p>
              )
            })}
          </div>
        )}
        {entries.length === 0 ? (
          <div className="empty-state">
            <BookOpenText size={30} />
            <h3>还没有长期记忆</h3>
            <p>添加关键人物、世界规则、待回收线索或重要时间节点。</p>
          </div>
        ) : (
          <div className="story-memory-entry-list">
            {entries.map(entry => (
              <article className={`story-memory-entry${entry.is_active ? '' : ' is-inactive'}`} key={entry.id}>
                <div className="story-memory-entry-heading">
                  <div>
                    {entry.review_status === 'pending' && (
                      <input
                        type="checkbox"
                        checked={selectedIds.includes(entry.id)}
                        onChange={() => toggleSelected(entry.id)}
                        aria-label={`选择${entry.title}`}
                      />
                    )}
                    <span className="memory-updated-label">
                      {categories.find(item => item.value === entry.category)?.label}
                    </span>
                    {entry.review_status === 'pending' && <span className="memory-review-badge pending">待审核</span>}
                    {entry.review_status === 'rejected' && <span className="memory-review-badge rejected">已拒绝</span>}
                    <h3>{entry.title}</h3>
                  </div>
                  <div className="story-memory-entry-actions">
                    {entry.review_status === 'pending' && (
                      <>
                        <button className="text-link" type="button" onClick={() => void review(entry, 'approved')}>
                          <Check size={15} />
                          通过
                        </button>
                        <button
                          className="text-link danger-link"
                          type="button"
                          onClick={() => void review(entry, 'rejected')}
                        >
                          <X size={15} />
                          拒绝
                        </button>
                      </>
                    )}
                    <button className="text-link" type="button" onClick={() => beginEdit(entry)}>
                      编辑
                    </button>
                    <button
                      className="text-link danger-link"
                      type="button"
                      onClick={() => void remove(entry)}
                      aria-label={`删除${entry.title}`}
                    >
                      <Trash2 size={15} />
                    </button>
                  </div>
                </div>
                <p>{entry.content}</p>
                {entry.keywords.length > 0 && <small>关键词：{entry.keywords.join('、')}</small>}
                {!entry.is_active && <small>已停用</small>}
              </article>
            ))}
          </div>
        )}
      </section>
    </div>
  )
}
