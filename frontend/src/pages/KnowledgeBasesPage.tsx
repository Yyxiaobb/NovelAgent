import { BookOpenCheck, FilePlus2, LoaderCircle, Plus, RefreshCw, Trash2, Upload } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { ApiError, api } from '../api/client'
import { Modal } from '../components/Modal'
import type { KnowledgeBase, KnowledgeDocument } from '../types'

const statusText: Record<string, string> = {
  pending: '等待索引',
  indexing: '正在索引',
  ready: '可用于检索',
  failed: '索引失败',
}

export function KnowledgeBasesPage() {
  const [bases, setBases] = useState<KnowledgeBase[]>([])
  const [documents, setDocuments] = useState<Record<number, KnowledgeDocument[]>>({})
  const [expanded, setExpanded] = useState<number[]>([])
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [createOpen, setCreateOpen] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<KnowledgeBase | null>(null)

  const refresh = useCallback(async () => {
    setError('')
    const items = await api.getKnowledgeBases()
    setBases(items)
    const availableIds = new Set(items.map(item => item.id))
    const expandedIds = (expanded.length ? expanded : items.map(item => item.id)).filter(id => availableIds.has(id))
    setExpanded(expandedIds)
    const results = await Promise.all(expandedIds.map(async id => [id, await api.getKnowledgeDocuments(id)] as const))
    setDocuments(current => ({ ...current, ...Object.fromEntries(results) }))
  }, [expanded])

  useEffect(() => {
    void refresh()
      .catch(reason => setError(reason instanceof Error ? reason.message : '知识库加载失败'))
      .finally(() => setLoading(false))
  }, [refresh])

  useEffect(() => {
    if (
      !Object.values(documents)
        .flat()
        .some(document => ['pending', 'indexing'].includes(document.status))
    )
      return
    const timer = window.setTimeout(() => {
      void refresh().catch(() => undefined)
    }, 2500)
    return () => window.clearTimeout(timer)
  }, [documents, refresh])

  async function createBase(event: React.FormEvent) {
    event.preventDefault()
    if (!name.trim()) return
    setBusy(true)
    setError('')
    try {
      const base = await api.createKnowledgeBase(name.trim(), description.trim())
      setName('')
      setDescription('')
      setCreateOpen(false)
      setExpanded(current => [...current, base.id])
      setNotice('知识库已创建')
      await refresh()
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '创建知识库失败')
    } finally {
      setBusy(false)
    }
  }

  async function importFile(base: KnowledgeBase, file?: File) {
    if (!file) return
    setBusy(true)
    setError('')
    setNotice('')
    try {
      const extension = file.name.split('.').pop()?.toLowerCase()
      if (!['txt', 'md', 'markdown'].includes(extension || '')) throw new Error('目前仅支持 TXT 和 Markdown 文件')
      const content = await file.text()
      if (content.length > 1_000_000) throw new Error('单个文档最多支持 100 万字符')
      await api.createKnowledgeDocument(base.id, file.name, content)
      setExpanded(current => (current.includes(base.id) ? current : [...current, base.id]))
      setNotice(`“${file.name}”已提交索引，完成后即可用于创作`)
      await refresh()
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '文档导入失败')
    } finally {
      setBusy(false)
    }
  }

  async function removeBase(base: KnowledgeBase) {
    setBusy(true)
    setError('')
    try {
      await api.deleteKnowledgeBase(base.id)
      setDeleteTarget(null)
      setExpanded(current => current.filter(id => id !== base.id))
      setDocuments(current => {
        const next = { ...current }
        delete next[base.id]
        return next
      })
      setNotice('知识库及文档已删除')
      await refresh()
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '删除知识库失败')
    } finally {
      setBusy(false)
    }
  }

  async function removeDocument(baseId: number, document: KnowledgeDocument) {
    setBusy(true)
    try {
      await api.deleteKnowledgeDocument(baseId, document.id)
      setDocuments(current => ({
        ...current,
        [baseId]: (current[baseId] || []).filter(item => item.id !== document.id),
      }))
      await refresh()
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '删除文档失败')
    } finally {
      setBusy(false)
    }
  }

  async function retryDocument(baseId: number, document: KnowledgeDocument) {
    setBusy(true)
    try {
      await api.retryKnowledgeDocument(baseId, document.id)
      await refresh()
      setNotice('已重新提交索引')
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : '重新索引失败')
    } finally {
      setBusy(false)
    }
  }

  if (loading)
    return (
      <div className="page">
        <p className="field-help">正在加载知识库…</p>
      </div>
    )

  return (
    <div className="page knowledge-page">
      <header className="page-header">
        <div>
          <p className="eyebrow">创作资料</p>
          <h1>知识库</h1>
          <p>整理你自己的设定、资料和参考文本，生成时可选择是否检索。</p>
        </div>
        <button className="primary-button knowledge-create-trigger" type="button" onClick={() => setCreateOpen(true)}>
          <Plus size={16} />
          新建知识库
        </button>
      </header>
      {error && (
        <p className="form-message error" role="alert">
          {error}
        </p>
      )}
      {notice && (
        <p className="form-message" role="status">
          {notice}
        </p>
      )}
      <section className="knowledge-base-list" aria-label="我的知识库">
        {bases.length === 0 ? (
          <div className="empty-state">
            <BookOpenCheck size={28} />
            <h3>还没有知识库</h3>
            <p>创建知识库并导入 TXT 或 Markdown 文档，开始将你的资料用于创作。</p>
          </div>
        ) : (
          bases.map(base => {
            const isExpanded = expanded.includes(base.id)
            const docs = documents[base.id] || []
            return (
              <article className="content-section knowledge-base-card" key={base.id}>
                <div className="knowledge-base-heading">
                  <button
                    className="knowledge-base-title"
                    type="button"
                    onClick={() =>
                      setExpanded(current =>
                        isExpanded ? current.filter(id => id !== base.id) : [...current, base.id],
                      )
                    }
                  >
                    <BookOpenCheck size={19} />
                    <span>
                      <strong>{base.name}</strong>
                      <small>
                        {base.description || '暂无说明'} · {base.ready_document_count}/{base.document_count} 份可检索
                      </small>
                    </span>
                  </button>
                  <div className="knowledge-base-actions">
                    <label className="secondary-button knowledge-upload-button">
                      <Upload size={15} />
                      导入 TXT / Markdown
                      <input
                        type="file"
                        accept=".txt,.md,.markdown,text/plain,text/markdown"
                        disabled={busy}
                        onChange={event => {
                          void importFile(base, event.target.files?.[0])
                          event.currentTarget.value = ''
                        }}
                      />
                    </label>
                    <button
                      className="icon-button danger-icon"
                      type="button"
                      title="删除知识库"
                      aria-label={`删除知识库 ${base.name}`}
                      disabled={busy}
                      onClick={() => setDeleteTarget(base)}
                    >
                      <Trash2 size={16} />
                    </button>
                  </div>
                </div>
                {isExpanded && (
                  <div className="knowledge-document-list">
                    {docs.length === 0 ? (
                      <p className="field-help">还没有文档，使用上方按钮导入 TXT 或 Markdown 文件。</p>
                    ) : (
                      docs.map(document => (
                        <div className="knowledge-document-item" key={document.id}>
                          <FilePlus2 size={17} />
                          <span className="knowledge-document-name">
                            <strong>{document.filename}</strong>
                            <small>
                              {document.chunk_count} 个文本片段 · {statusText[document.status] || document.status}
                              {document.error_message ? ` · ${document.error_message}` : ''}
                            </small>
                          </span>
                          {['pending', 'indexing'].includes(document.status) && (
                            <LoaderCircle className="spin" size={16} aria-label="索引中" />
                          )}
                          {document.status === 'failed' && (
                            <button
                              className="text-link"
                              type="button"
                              onClick={() => void retryDocument(base.id, document)}
                              disabled={busy}
                            >
                              <RefreshCw size={14} />
                              重试
                            </button>
                          )}
                          <button
                            className="icon-button"
                            type="button"
                            title="删除文档"
                            aria-label={`删除文档 ${document.filename}`}
                            disabled={busy}
                            onClick={() => void removeDocument(base.id, document)}
                          >
                            <Trash2 size={15} />
                          </button>
                        </div>
                      ))
                    )}
                  </div>
                )}
              </article>
            )
          })
        )}
      </section>
      <p className="knowledge-footnote">索引状态为“可用于检索”后，创作时才能引用相应资料。文档内容只对你的账号开放。</p>
      <Modal open={createOpen} title="新建知识库" onClose={() => !busy && setCreateOpen(false)} busy={busy}>
        <form className="knowledge-create-form" onSubmit={event => void createBase(event)}>
          <label className="detail-edit-field">
            <span>知识库名称</span>
            <input
              value={name}
              onChange={event => setName(event.target.value)}
              maxLength={100}
              required
              autoFocus
              placeholder="例如：世界观设定、历史资料"
            />
          </label>
          <label className="detail-edit-field">
            <span>说明（选填）</span>
            <input
              value={description}
              onChange={event => setDescription(event.target.value)}
              maxLength={500}
              placeholder="简要说明这组资料的用途"
            />
          </label>
          <div className="modal-actions">
            <button className="secondary-button" type="button" onClick={() => setCreateOpen(false)} disabled={busy}>
              取消
            </button>
            <button className="primary-button" type="submit" disabled={busy || !name.trim()}>
              <Plus size={15} />
              创建知识库
            </button>
          </div>
        </form>
      </Modal>
      <Modal open={Boolean(deleteTarget)} title="删除知识库" onClose={() => !busy && setDeleteTarget(null)} busy={busy}>
        <div className="knowledge-delete-confirm">
          <Trash2 size={26} />
          <p>
            确定删除“<strong>{deleteTarget?.name}</strong>”及其中全部文档吗？
          </p>
          <small>删除后无法恢复，请确认后继续。</small>
        </div>
        <div className="modal-actions">
          <button className="secondary-button" type="button" onClick={() => setDeleteTarget(null)} disabled={busy}>
            取消
          </button>
          <button
            className="destructive-button"
            type="button"
            onClick={() => deleteTarget && void removeBase(deleteTarget)}
            disabled={busy || !deleteTarget}
          >
            {busy ? '正在删除…' : '确认删除'}
          </button>
        </div>
      </Modal>
    </div>
  )
}
