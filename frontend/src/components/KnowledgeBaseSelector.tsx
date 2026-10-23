import { BookOpenCheck, ChevronDown, ChevronUp } from 'lucide-react'
import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { KnowledgeBase } from '../types'

interface Props {
  selectedIds: number[]
  onChange: (ids: number[]) => void
}

export function KnowledgeBaseSelector({ selectedIds, onChange }: Props) {
  const [open, setOpen] = useState(false)
  const [bases, setBases] = useState<KnowledgeBase[]>([])
  const [error, setError] = useState('')

  useEffect(() => {
    if (!open || bases.length) return
    void api
      .getKnowledgeBases()
      .then(setBases)
      .catch(reason => {
        setError(reason instanceof Error ? reason.message : '知识库暂时无法加载')
      })
  }, [open, bases.length])

  function toggle(id: number) {
    onChange(selectedIds.includes(id) ? selectedIds.filter(item => item !== id) : [...selectedIds, id])
  }

  return (
    <section className="knowledge-selector" aria-label="选择创作知识库">
      <button className="knowledge-selector-toggle" type="button" onClick={() => setOpen(value => !value)}>
        <span>
          <BookOpenCheck size={16} />
          使用知识库（可选）
        </span>
        <span className="knowledge-selector-summary">
          {selectedIds.length ? `已选 ${selectedIds.length} 个` : '不调用知识库'}
        </span>
        {open ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
      </button>
      {open && (
        <div className="knowledge-selector-options">
          {error && (
            <p className="form-message error" role="alert">
              {error}
            </p>
          )}
          {!error && bases.length === 0 && <p className="field-help">暂无知识库，可前往“知识库”创建并导入资料。</p>}
          {bases.map(base => (
            <label className="knowledge-selector-option" key={base.id}>
              <input type="checkbox" checked={selectedIds.includes(base.id)} onChange={() => toggle(base.id)} />
              <span>
                <strong>{base.name}</strong>
                <small>
                  {base.ready_document_count}/{base.document_count} 份文档可检索
                </small>
              </span>
            </label>
          ))}
          <p className="field-help">只会检索已完成索引的文档；每次生成可单独选择。</p>
        </div>
      )}
    </section>
  )
}
