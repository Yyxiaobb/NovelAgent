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

export interface Project {
  id: number
  projectname: string | null
  introduction: string | null
  project_type?: string | null
  cover_url?: string | null
  outline?: string | null
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
}

export interface ChapterPlan {
  objective: string
  conflict: string
  key_events: string
  ending_hook: string
  expected_words: number
}

export interface ChapterMemory {
  character_state: string
  setting_changes: string
  unresolved_threads: string
  timeline: string
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
  error: string | null
  created_at: string
  updated_at: string
  finished_at: string | null
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
