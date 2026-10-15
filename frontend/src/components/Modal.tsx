import { X } from 'lucide-react'
import { useEffect, useId, type ReactNode } from 'react'

interface ModalProps {
  open: boolean
  title: string
  onClose: () => void
  children: ReactNode
  busy?: boolean
}

export function Modal({ open, title, onClose, children, busy = false }: ModalProps) {
  const titleId = useId()
  useEffect(() => {
    if (!open) return
    const handleKey = (event: KeyboardEvent) => event.key === 'Escape' && !busy && onClose()
    window.addEventListener('keydown', handleKey)
    return () => window.removeEventListener('keydown', handleKey)
  }, [open, onClose, busy])

  if (!open) return null

  return (
    <div className="modal-backdrop" onMouseDown={() => !busy && onClose()} role="presentation">
      <section className="modal" role="dialog" aria-modal="true" aria-labelledby={titleId} aria-busy={busy} onMouseDown={(event) => event.stopPropagation()}>
        <div className="modal-header">
          <h2 id={titleId}>{title}</h2>
          <button className="icon-button" type="button" onClick={onClose} aria-label="关闭" disabled={busy}>
            <X size={19} />
          </button>
        </div>
        {children}
      </section>
    </div>
  )
}
