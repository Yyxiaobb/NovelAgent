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
  token: string
  userInfo: User
}

export interface Project {
  id: number
  projectname: string | null
  introduction: string | null
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
  created_at: string
  updated_at: string
  is_deleted: boolean
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
