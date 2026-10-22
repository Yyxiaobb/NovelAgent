import { Check, FilePenLine, Lightbulb, Plus, Save, Sparkles, Trash2 } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { api } from '../api/client'
import { Modal } from '../components/Modal'
import type { Inspiration } from '../types'

const dateFormat = new Intl.DateTimeFormat('zh-CN', {
  month: 'short',
  day: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
})

export function InspirationsPage() {
  const [items, setItems] = useState<Inspiration[]>([])
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [title, setTitle] = useState('')
  const [content, setContent] = useState('')
  const [refinedContent, setRefinedContent] = useState('')
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [deleteOpen, setDeleteOpen] = useState(false)

  const selected = useMemo(() => items.find(item => item.id === selectedId) || null, [items, selectedId])

  const load = useCallback(async () => {
    setError('')
    const result = await api.getInspirations()
    setItems(result)
    if (selectedId && result.some(item => item.id === selectedId)) return
    if (result[0]) {
      setSelectedId(result[0].id)
      setTitle(result[0].title)
      setContent(result[0].content)
      setRefinedContent(result[0].refined_content || '')
    }
  }, [selectedId])

  useEffect(() => {
    void load()
      .catch(reason => setError(reason instanceof Error ? reason.message : '灵感加载失败'))
      .finally(() => setLoading(false))
  }, [load])

  function selectItem(item: Inspiration) {
    setSelectedId(item.id)
    setTitle(item.title)
    setContent(item.content)
    setRefinedContent(item.refined_content || '')
    setNotice('')
    setError('')
  }

  function createDraft() {
    setSelectedId(null)
    setTitle('')
    setContent('')
    setRefinedContent('')
    setNotice('')
    setError('')
  }

  async function save() {
    if (!title.trim() || !content.trim() || busy) {
      setError('请填写灵感标题和内容')
      return null
    }
    setBusy(true)
    setError('')
    setNotice('')
    try {
      const item = selectedId
        ? await api.updateInspiration(selectedId, title.trim(), content.trim(), refinedContent.trim() || null)
        : await api.createInspiration(title.trim(), content.trim())
      setItems(current => {
        const exists = current.some(entry => entry.id === item.id)
        return exists ? current.map(entry => (entry.id === item.id ? item : entry)) : [item, ...current]
      })
      setSelectedId(item.id)
      setTitle(item.title)
      setContent(item.content)
      setRefinedContent(item.refined_content || '')
      setNotice('灵感已保存')
      return item
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '保存灵感失败')
      return null
    } finally {
      setBusy(false)
    }
  }

  async function refine() {
    let item = selected
    if (!item || item.title !== title || item.content !== content) item = await save()
    if (!item || busy) return
    setBusy(true)
    setError('')
    setNotice('')
    try {
      const result = await api.refineInspiration(item.id)
      setRefinedContent(result.refined_content || '')
      setItems(current => current.map(entry => (entry.id === result.id ? result : entry)))
      setNotice('创意已完善，可以继续修改后保存')
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '完善创意失败')
    } finally {
      setBusy(false)
    }
  }

  async function remove() {
    if (!selectedId || busy) return
    setBusy(true)
    setError('')
    try {
      await api.deleteInspiration(selectedId)
      const remaining = items.filter(item => item.id !== selectedId)
      setItems(remaining)
      setDeleteOpen(false)
      if (remaining[0]) selectItem(remaining[0])
      else createDraft()
      setNotice('灵感已移入回收站')
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '删除灵感失败')
    } finally {
      setBusy(false)
    }
  }

  if (loading)
    return (
      <div className="page">
        <p className="field-help">正在加载灵感库…</p>
      </div>
    )

  return (
    <div className="page inspiration-page">
      <header className="page-header">
        <div>
          <p className="eyebrow">创作工具</p>
          <h1>灵感库</h1>
          <p>把零散的念头保存下来，随时完善成可以继续创作的故事提案。</p>
        </div>
        <button className="primary-button" type="button" onClick={createDraft}>
          <Plus size={17} />
          新建灵感
        </button>
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
      <div className="inspiration-layout">
        <aside className="inspiration-list" aria-label="灵感列表">
          <div className="inspiration-list-heading">
            <span>我的灵感</span>
            <strong>{items.length}</strong>
          </div>
          {items.length === 0 ? (
            <div className="inspiration-list-empty">
              <Lightbulb size={25} />
              <p>还没有保存的灵感</p>
              <button className="text-link" type="button" onClick={createDraft}>
                现在创建一个
              </button>
            </div>
          ) : (
            items.map(item => (
              <button
                className={`inspiration-list-item ${item.id === selectedId ? 'active' : ''}`}
                key={item.id}
                type="button"
                onClick={() => selectItem(item)}
              >
                <span className="inspiration-list-icon">
                  <Lightbulb size={16} />
                </span>
                <span>
                  <strong>{item.title}</strong>
                  <small>{dateFormat.format(new Date(item.updated_at))}</small>
                </span>
              </button>
            ))
          )}
        </aside>
        <section className="inspiration-editor" aria-label="灵感编辑器">
          <div className="inspiration-editor-heading">
            <div>
              <span className="eyebrow">{selected ? '编辑灵感' : '新灵感'}</span>
              <h2>{selected ? '继续打磨你的想法' : '记录一个新念头'}</h2>
            </div>
            {selected && (
              <button
                className="icon-button danger-icon"
                type="button"
                aria-label="删除灵感"
                title="删除灵感"
                onClick={() => setDeleteOpen(true)}
                disabled={busy}
              >
                <Trash2 size={17} />
              </button>
            )}
          </div>
          <label className="field">
            <span>标题</span>
            <input
              value={title}
              onChange={event => setTitle(event.target.value)}
              placeholder="例如：会听见城市记忆的修表匠"
              maxLength={100}
            />
          </label>
          <label className="field">
            <span>原始灵感</span>
            <textarea
              value={content}
              onChange={event => setContent(event.target.value)}
              placeholder="写下人物、场景、冲突，哪怕只是一句话……"
              maxLength={5000}
            />
            <small>{content.length}/5000</small>
          </label>
          <div className="inspiration-editor-actions">
            <button
              className="secondary-button"
              type="button"
              onClick={() => void refine()}
              disabled={busy || !content.trim()}
            >
              <Sparkles size={16} />
              {busy ? '处理中…' : '完善创意'}
            </button>
            <button className="primary-button" type="button" onClick={() => void save()} disabled={busy}>
              <Save size={16} />
              保存灵感
            </button>
          </div>
          {refinedContent && (
            <label className="field inspiration-refined-field">
              <span>
                <Check size={15} />
                完善后的创意
              </span>
              <textarea
                value={refinedContent}
                onChange={event => setRefinedContent(event.target.value)}
                maxLength={20000}
              />
              <small>{refinedContent.length}/20000 · 可修改后保存</small>
            </label>
          )}
          {!selected && !refinedContent && (
            <div className="inspiration-editor-tip">
              <FilePenLine size={18} />
              <p>先保存灵感，再使用“完善创意”调用模型生成故事提案。</p>
            </div>
          )}
        </section>
      </div>
      <Modal open={deleteOpen} title="删除灵感" onClose={() => !busy && setDeleteOpen(false)} busy={busy}>
        <div className="modal-body form-stack">
          <div className="project-action-summary destructive">
            <Trash2 size={23} />
            <div>
              <strong>{title || '未命名灵感'}</strong>
              <p>灵感会移入回收站，之后可以还原；在回收站彻底删除后将无法恢复。</p>
            </div>
          </div>
          <div className="modal-actions">
            <button className="secondary-button" type="button" onClick={() => setDeleteOpen(false)} disabled={busy}>
              取消
            </button>
            <button
              className="primary-button destructive-button"
              type="button"
              onClick={() => void remove()}
              disabled={busy}
            >
              {busy ? '正在删除…' : '移入回收站'}
            </button>
          </div>
        </div>
      </Modal>
    </div>
  )
}
