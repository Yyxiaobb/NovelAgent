import { BookOpenCheck } from 'lucide-react'
import type { KnowledgeCitation } from '../types'

export function KnowledgeCitationList({ citations }: { citations: KnowledgeCitation[] }) {
  if (!citations.length) return null
  return (
    <section className="knowledge-citations" aria-label="知识库来源">
      <strong>
        <BookOpenCheck size={15} />
        本次参考的知识库资料
      </strong>
      {citations.map((citation, index) => (
        <details key={`${citation.document_id}-${citation.chunk_index}-${index}`}>
          <summary>
            【{index + 1}】{citation.knowledge_base_name} · {citation.filename} · 片段 {citation.chunk_index + 1}
          </summary>
          <p>{citation.excerpt}</p>
          <small>相关度 {(citation.similarity * 100).toFixed(0)}%</small>
        </details>
      ))}
    </section>
  )
}
