import { ChevronDown, ChevronUp, Lightbulb } from 'lucide-react'
import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { Inspiration } from '../types'

interface Props {
  selectedIds: number[]
  onChange: (ids: number[]) => void
  onItemsChange?: (items: Inspiration[]) => void
}

export function InspirationSelector({ selectedIds, onChange, onItemsChange }: Props) {
  const [open, setOpen] = useState(false)
  const [items, setItems] = useState<Inspiration[]>([])
  const [error, setError] = useState('')

  useEffect(() => {
    if (!open || items.length) return
    void api
      .getInspirations()
      .then(result => {
        setItems(result)
        onItemsChange?.(result)
      })
      .catch(reason => {
        setError(reason instanceof Error ? reason.message : '灵感暂时无法加载')
      })
  }, [items.length, onItemsChange, open])

  function toggle(id: number) {
    onChange(selectedIds.includes(id) ? selectedIds.filter(item => item !== id) : [...selectedIds, id])
  }

  return (
    <section className="knowledge-selector" aria-label="选择注入灵感">
      <button className="knowledge-selector-toggle" type="button" onClick={() => setOpen(value => !value)}>
        <span>
          <Lightbulb size={16} />
          注入已有灵感（可选）
        </span>
        <span className="knowledge-selector-summary">
          {selectedIds.length ? `已选 ${selectedIds.length} 条` : '不注入灵感'}
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
          {!error && items.length === 0 && <p className="field-help">暂无已保存灵感，可先前往“灵感库”创建。</p>}
          {items.map(item => (
            <label className="knowledge-selector-option" key={item.id}>
              <input
                type="checkbox"
                aria-label={item.title}
                checked={selectedIds.includes(item.id)}
                onChange={() => toggle(item.id)}
              />
              <span>
                <strong>{item.title}</strong>
                <small>{item.refined_content ? '已完善，生成时优先使用完善内容' : '使用原始灵感内容'}</small>
              </span>
            </label>
          ))}
          <p className="field-help">选中的灵感会在生成时作为独立参考注入，不会改写“你的想法”；每条内容会自动限长。</p>
        </div>
      )}
    </section>
  )
}
