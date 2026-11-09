export type Gender = 'male' | 'female' | 'unknown'

export interface User {
  id: number
  username: string
  nickname: string | null
  avatar: string | null
  gender: Gender | null
  bio: string | null
  phone?: string | null
}

export interface AuthData {
  token?: string | null
  userInfo: User
}

export interface Inspiration {
  id: number
  title: string
  content: string
  refined_content: string | null
  is_deleted?: boolean
  created_at: string
  updated_at: string
}

export interface Project {
  id: number
  projectname: string | null
  introduction: string | null
  project_type?: string | null
  cover_url?: string | null
  outline?: string | null
  current_state_markdown?: string | null
  expected_words?: number | null
  total_words: number
  chapter_count: number
  created_at: string
  updated_at: string
  status: string | null
}

export interface Chapter {
  id: number
  project_id: number
  chapter_number: number
  chaptername: string | null
  content?: string | null
  plan?: ChapterPlan | null
  summary?: string | null
  memory?: ChapterMemory | null
  created_at: string
  updated_at: string
  is_deleted: boolean
  volume_id?: number | null
  word_count?: number
}

export interface ChapterPlan {
  objective: string
  conflict: string
  key_events: string
  ending_hook: string
  expected_words: number
}

export interface OutlineVolume {
  id: number
  project_id: number
  volume_number: number
  name: string
  start_chapter?: number | null
  end_chapter?: number | null
  outline: string | null
  is_completed?: boolean
  completion_note?: string | null
  completed_at?: string | null
  is_deleted?: boolean
  created_at: string
  updated_at: string
}

export interface RecycledOutlineVolume extends OutlineVolume {
  projectname: string | null
  project_status: string | null
}

export interface ChapterMemory {
  character_state: string
  setting_changes: string
  unresolved_threads: string
  timeline: string
}

export type StoryMemoryCategory = 'character' | 'world' | 'thread' | 'timeline'

export interface StoryMemoryEntry {
  id: number
  project_id: number
  category: StoryMemoryCategory
  title: string
  content: string
  keywords: string[]
  source_chapter_id: number | null
  is_active: boolean
  review_status: 'pending' | 'approved' | 'rejected'
  origin: 'manual' | 'chapter_extract'
  merged_into_id: number | null
  created_at: string
  updated_at: string
}

export interface StoryMemoryPayload {
  category: StoryMemoryCategory
  title: string
  content: string
  keywords: string[]
  source_chapter_id: number | null
  is_active: boolean
}

export interface StoryMemoryConflict {
  first_id: number
  second_id: number
  category: StoryMemoryCategory
  similarity: number
  reason: 'same_title' | 'shared_keywords' | 'similar_content'
}

export interface StoryMemoryEvent {
  id: number
  project_id: number
  actor_user_id: number
  event_type:
    'review' | 'batch_review' | 'merge' | 'update' | 'undo_review' | 'undo_batch_review' | 'undo_merge' | 'undo_update'
  memory_id: number | null
  related_memory_ids: number[]
  details: Record<string, unknown>
  created_at: string
}

export interface KnowledgeBase {
  id: number
  name: string
  description: string | null
  document_count: number
  ready_document_count: number
  created_at: string
  updated_at: string
  is_deleted?: boolean
}

export interface KnowledgeDocument {
  id: number
  knowledge_base_id: number
  filename: string
  status: 'pending' | 'indexing' | 'ready' | 'failed' | string
  error_message: string | null
  chunk_count: number
  created_at: string
  updated_at: string
}

export interface KnowledgeCitation {
  knowledge_base_id: number
  knowledge_base_name: string
  document_id: number
  filename: string
  chunk_index: number
  similarity: number
  excerpt: string
}

export interface GenerationJob {
  job_id: string
  project_id: number
  chapter_id: number | null
  job_type: string
  status: 'queued' | 'running' | 'completed' | 'failed' | 'cancelled' | string
  progress: number
  content: string
  expected_words?: number | null
  plan?: ChapterPlan | null
  citations?: KnowledgeCitation[]
  generation_info?: {
    model?: string
    prompt_template_id?: string
    prompt_template_version?: string
    segments?: number
    quality_check?: string
    review_enabled?: boolean
    review_rounds?: number
    review_final_score?: number | null
    review_stop_reason?: string
    review_error?: string | null
    review_history?: GenerationReviewIteration[]
  }
  error: string | null
  created_at: string
  updated_at: string
  finished_at: string | null
}

export interface GenerationReviewIssue {
  id: string
  category: string
  severity: string
  evidence: string
  suggestion: string
  must_fix: boolean
}

export interface GenerationReview {
  overall_score: number
  summary: string
  strengths: string[]
  issues: GenerationReviewIssue[]
  dimension_scores: Record<string, number>
  stop_recommendation: boolean
}

export interface GenerationReviewIteration {
  round: number
  score: number
  review: GenerationReview
}

export interface ChapterVersion {
  id: number
  chapter_id: number
  version_number: number
  source: string
  chapter_number: number
  chaptername: string | null
  content: string | null
  plan: ChapterPlan | null
  summary: string | null
  memory: ChapterMemory | null
  created_at: string
}

export interface OutlineVersion {
  id: number
  project_id: number
  version_number: number
  source: string
  outline: string | null
  created_at: string
}

export interface OutlineVolumeVersion {
  id: number
  project_id: number
  volume_id: number
  version_number: number
  source: string
  volume_number: number
  name: string
  start_chapter: number | null
  end_chapter: number | null
  outline: string | null
  created_at: string
}

export interface RecycledChapter extends Chapter {
  projectname: string | null
  project_status: string | null
}

export interface ApiResponse<T> {
  code: number
  message: string
  data: T
}

export interface ProfilePayload {
  nickname?: string
  avatar?: string
  gender?: Gender
  bio?: string
  phone?: string
}
