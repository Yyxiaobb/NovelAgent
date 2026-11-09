import { RotateCcw, Trash2 } from 'lucide-react'

interface DraftRecoveryBannerProps {
  savedAt: string
  onRestore: () => void
  onDiscard: () => void
}

export function DraftRecoveryBanner({ savedAt, onRestore, onDiscard }: DraftRecoveryBannerProps) {
  const timestamp = new Date(savedAt)
  return (
    <section className="draft-recovery-banner" aria-label="发现本地草稿">
      <div className="draft-recovery-copy">
        <strong>发现未同步到作品的本地草稿</strong>
        <span>
          自动暂存于此设备： <time dateTime={savedAt}>{timestamp.toLocaleString()}</time>
        </span>
      </div>
      <div className="draft-recovery-actions">
        <button className="secondary-button" type="button" onClick={onDiscard}>
          <Trash2 size={14} />
          丢弃草稿
        </button>
        <button className="primary-button" type="button" onClick={onRestore}>
          <RotateCcw size={14} />
          恢复草稿
        </button>
      </div>
    </section>
  )
}
