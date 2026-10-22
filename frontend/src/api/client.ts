import type {
  ApiResponse,
  AuthData,
  Chapter,
  ChapterMemory,
  ChapterPlan,
  ChapterVersion,
  GenerationJob,
  KnowledgeBase,
  KnowledgeDocument,
  KnowledgeCitation,
  Inspiration,
  OutlineVersion,
  ProfilePayload,
  Project,
  RecycledChapter,
  StoryMemoryEntry,
  StoryMemoryEvent,
  StoryMemoryConflict,
  StoryMemoryPayload,
  User,
} from '../types'

const TOKEN_KEY = 'novel-agent-token'

export class ApiError extends Error {
  status: number

  constructor(message: string, status = 0) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

function errorMessage(payload: unknown): string {
  if (!payload || typeof payload !== 'object') return '请求失败，请稍后重试'
  const body = payload as { detail?: string | Array<{ msg?: string }>; message?: string }
  if (typeof body.detail === 'string') return body.detail
  if (Array.isArray(body.detail))
    return body.detail
      .map(item => item.msg)
      .filter(Boolean)
      .join('；')
  return body.message || '请求失败，请稍后重试'
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = localStorage.getItem(TOKEN_KEY)
  const headers = new Headers(options.headers)
  if (options.body) headers.set('Content-Type', 'application/json')
  if (token) headers.set('Authorization', `Bearer ${token}`)

  let response: Response
  try {
    response = await fetch(path, { ...options, headers, credentials: 'include' })
  } catch {
    throw new ApiError('无法连接服务器，请确认后端服务已启动')
  }

  const payload = await response.json().catch(() => null)
  if (!response.ok) throw new ApiError(errorMessage(payload), response.status)

  const envelope = payload as ApiResponse<T>
  if (typeof envelope.code === 'number' && envelope.code !== 200) {
    throw new ApiError(envelope.message || '请求失败', response.status)
  }
  return envelope.data
}

async function streamChapterContent(
  path: string,
  body: unknown,
  onChunk?: (chunk: string) => void,
): Promise<{ content: string; meta: { expected_words: number; plan: ChapterPlan; citations?: KnowledgeCitation[] } }> {
  const token = localStorage.getItem(TOKEN_KEY)
  const headers = new Headers({ 'Content-Type': 'application/json' })
  if (token) headers.set('Authorization', `Bearer ${token}`)
  const response = await fetch(path, { method: 'POST', headers, body: JSON.stringify(body), credentials: 'include' })
  if (!response.ok || !response.body) {
    const payload = await response.json().catch(() => null)
    throw new ApiError(errorMessage(payload), response.status)
  }
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let content = ''
  let meta: { expected_words: number; plan: ChapterPlan; citations?: KnowledgeCitation[] } | null = null
  const consume = (block: string) => {
    const line = block.split('\n').find(item => item.startsWith('data:'))
    if (!line) return
    const event = JSON.parse(line.slice(5).trim()) as { event: string; data: unknown }
    if (event.event === 'chunk') {
      const chunk = String(event.data)
      content += chunk
      onChunk?.(chunk)
    } else if (event.event === 'done') {
      meta = event.data as { expected_words: number; plan: ChapterPlan }
    } else if (event.event === 'error') {
      throw new ApiError(String(event.data))
    }
  }
  while (true) {
    const { value, done } = await reader.read()
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done })
    const blocks = buffer.split('\n\n')
    buffer = blocks.pop() || ''
    blocks.forEach(consume)
    if (done) break
  }
  if (buffer.trim()) consume(buffer)
  if (!meta) throw new ApiError('模型未返回完整章节内容')
  return { content, meta }
}

export const tokenStore = {
  key: TOKEN_KEY,
  get: () => localStorage.getItem(TOKEN_KEY),
  set: (token: string) => localStorage.setItem(TOKEN_KEY, token),
  clear: () => localStorage.removeItem(TOKEN_KEY),
}

export const api = {
  login: (username: string, password: string) =>
    request<AuthData>('/api/user/login', { method: 'POST', body: JSON.stringify({ username, password }) }),
  register: (username: string, password: string) =>
    request<AuthData>('/api/user/register', { method: 'POST', body: JSON.stringify({ username, password }) }),
  getProfile: () => request<User>('/api/user/info'),
  updateProfile: (payload: ProfilePayload) =>
    request<User>('/api/user/update', { method: 'PUT', body: JSON.stringify(payload) }),
  uploadAvatar: (dataUrl: string, filename: string) =>
    request<User>('/api/user/avatar/upload', {
      method: 'POST',
      body: JSON.stringify({ data_url: dataUrl, filename }),
    }),
  changePassword: (oldPassword: string, newPassword: string) =>
    request<null>('/api/user/password', {
      method: 'PUT',
      body: JSON.stringify({ oldPassword, newPassword }),
    }),
  logout: () => request<null>('/api/user/logout', { method: 'POST' }),
  getProjects: () => request<Project[]>('/api/project/projects'),
  getInspirations: () => request<Inspiration[]>('/api/inspirations'),
  createInspiration: (title: string, content: string) =>
    request<Inspiration>('/api/inspirations', {
      method: 'POST',
      body: JSON.stringify({ title, content }),
    }),
  updateInspiration: (id: number, title: string, content: string, refinedContent: string | null) =>
    request<Inspiration>(`/api/inspirations/${id}`, {
      method: 'PUT',
      body: JSON.stringify({ title, content, refined_content: refinedContent }),
    }),
  refineInspiration: (id: number) => request<Inspiration>(`/api/inspirations/${id}/refine`, { method: 'POST' }),
  deleteInspiration: (id: number) =>
    request<{ id: number; is_deleted: boolean }>(`/api/inspirations/${id}`, { method: 'DELETE' }),
  getKnowledgeBases: () => request<KnowledgeBase[]>('/api/knowledge-bases'),
  createKnowledgeBase: (name: string, description: string) =>
    request<KnowledgeBase>('/api/knowledge-bases', {
      method: 'POST',
      body: JSON.stringify({ name, description: description || null }),
    }),
  deleteKnowledgeBase: (baseId: number) =>
    request<{ id: number }>(`/api/knowledge-bases/${baseId}`, { method: 'DELETE' }),
  getKnowledgeDocuments: (baseId: number) => request<KnowledgeDocument[]>(`/api/knowledge-bases/${baseId}/documents`),
  createKnowledgeDocument: (baseId: number, filename: string, content: string) =>
    request<KnowledgeDocument>(`/api/knowledge-bases/${baseId}/documents`, {
      method: 'POST',
      body: JSON.stringify({ filename, content }),
    }),
  deleteKnowledgeDocument: (baseId: number, documentId: number) =>
    request<{ id: number }>(`/api/knowledge-bases/${baseId}/documents/${documentId}`, { method: 'DELETE' }),
  retryKnowledgeDocument: (baseId: number, documentId: number) =>
    request<KnowledgeDocument>(`/api/knowledge-bases/${baseId}/documents/${documentId}/retry`, { method: 'POST' }),
  getProject: (projectId: number) => request<Project>(`/api/project/detail/${projectId}`),
  uploadProjectCover: (projectId: number, dataUrl: string, filename: string) =>
    request<Project>(`/api/project/${projectId}/cover/upload`, {
      method: 'POST',
      body: JSON.stringify({ data_url: dataUrl, filename }),
    }),
  generateProjectCover: (projectId: number) =>
    request<Project>(`/api/agent/projects/${projectId}/cover`, { method: 'POST' }),
  getProjectMemories: (projectId: number) => request<StoryMemoryEntry[]>(`/api/project/${projectId}/memories`),
  getProjectMemoryConflicts: (projectId: number) =>
    request<StoryMemoryConflict[]>(`/api/project/${projectId}/memories/conflicts`),
  getProjectMemoryEvents: (projectId: number, limit = 50) =>
    request<StoryMemoryEvent[]>(`/api/project/${projectId}/memories/events?limit=${limit}`),
  createProjectMemory: (projectId: number, payload: StoryMemoryPayload) =>
    request<StoryMemoryEntry>(`/api/project/${projectId}/memories`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  updateProjectMemory: (projectId: number, memoryId: number, payload: StoryMemoryPayload) =>
    request<StoryMemoryEntry>(`/api/project/${projectId}/memories/${memoryId}`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),
  deleteProjectMemory: (projectId: number, memoryId: number) =>
    request<{ id: number }>(`/api/project/${projectId}/memories/${memoryId}`, { method: 'DELETE' }),
  reviewProjectMemory: (projectId: number, memoryId: number, decision: 'approved' | 'rejected') =>
    request<StoryMemoryEntry>(`/api/project/${projectId}/memories/${memoryId}/review`, {
      method: 'POST',
      body: JSON.stringify({ decision }),
    }),
  undoProjectMemory: (projectId: number, memoryId: number, eventId?: number) =>
    request<StoryMemoryEntry>(
      `/api/project/${projectId}/memories/${memoryId}/undo${eventId ? `?event_id=${eventId}` : ''}`,
      { method: 'POST' },
    ),
  batchReviewProjectMemories: (projectId: number, memoryIds: number[], decision: 'approved' | 'rejected') =>
    request<StoryMemoryEntry[]>(`/api/project/${projectId}/memories/batch-review`, {
      method: 'POST',
      body: JSON.stringify({ memory_ids: memoryIds, decision }),
    }),
  mergeProjectMemories: (projectId: number, targetId: number, sourceIds: number[]) =>
    request<StoryMemoryEntry>(`/api/project/${projectId}/memories/merge`, {
      method: 'POST',
      body: JSON.stringify({ target_id: targetId, source_ids: sourceIds }),
    }),
  exportProject: async (projectId: number, format: 'markdown' | 'txt'): Promise<Blob> => {
    const token = localStorage.getItem(TOKEN_KEY)
    const headers = new Headers()
    if (token) headers.set('Authorization', `Bearer ${token}`)
    let response: Response
    try {
      response = await fetch(`/api/project/${projectId}/export/${format}`, { headers, credentials: 'include' })
    } catch {
      throw new ApiError('无法连接服务器，请确认后端服务已启动')
    }
    if (!response.ok) {
      const payload = await response.json().catch(() => null)
      throw new ApiError(errorMessage(payload), response.status)
    }
    return response.blob()
  },
  getProjectChapters: (projectId: number) => request<Chapter[]>(`/api/project/${projectId}/chapters`),
  getProjectOutline: (projectId: number) =>
    request<{ project_id: number; outline: string | null }>(`/api/project/${projectId}/outline`),
  updateProjectOutline: (projectId: number, outline: string) =>
    request<{ project_id: number; outline: string | null }>(`/api/project/${projectId}/outline`, {
      method: 'PUT',
      body: JSON.stringify({ outline }),
    }),
  getOutlineVersions: (projectId: number, limit = 50) =>
    request<OutlineVersion[]>(`/api/project/${projectId}/outline/versions?limit=${limit}`),
  restoreOutlineVersion: (projectId: number, versionId: number) =>
    request<{ project_id: number; outline: string | null }>(
      `/api/project/${projectId}/outline/versions/${versionId}/restore`,
      { method: 'POST' },
    ),
  generateProjectOutline: (projectId: number, expectedWords: number, userIdea = '', knowledgeBaseIds: number[] = []) =>
    request<{ project_id: number; expected_words: number; outline: string; citations?: KnowledgeCitation[] }>(
      `/api/agent/projects/${projectId}/outline`,
      {
        method: 'POST',
        body: JSON.stringify({
          expected_words: expectedWords,
          user_idea: userIdea,
          knowledge_base_ids: knowledgeBaseIds,
        }),
      },
    ),
  generateChapterPlan: (
    projectId: number,
    chapterId: number,
    expectedWords = 3000,
    userIdea = '',
    knowledgeBaseIds: number[] = [],
  ) =>
    request<{ project_id: number; chapter_id: number; plan: ChapterPlan; citations?: KnowledgeCitation[] }>(
      `/api/agent/projects/${projectId}/chapters/${chapterId}/plan`,
      {
        method: 'POST',
        body: JSON.stringify({
          expected_words: expectedWords,
          user_idea: userIdea,
          knowledge_base_ids: knowledgeBaseIds,
        }),
      },
    ),
  generateChapterContent: (
    projectId: number,
    chapterId: number,
    plan: ChapterPlan,
    userIdea = '',
    knowledgeBaseIds: number[] = [],
  ) =>
    request<{
      project_id: number
      chapter_id: number
      expected_words: number
      plan: ChapterPlan
      content: string
      citations?: KnowledgeCitation[]
    }>(`/api/agent/projects/${projectId}/chapters/${chapterId}/content`, {
      method: 'POST',
      body: JSON.stringify({ plan, user_idea: userIdea, knowledge_base_ids: knowledgeBaseIds }),
    }),
  generateChapterContentStream: async (
    projectId: number,
    chapterId: number,
    plan: ChapterPlan,
    userIdea = '',
    onChunk?: (chunk: string) => void,
    knowledgeBaseIds: number[] = [],
  ) => {
    const body = { plan, user_idea: userIdea, knowledge_base_ids: knowledgeBaseIds }
    if (plan.expected_words < 5000) {
      const result = await streamChapterContent(
        `/api/agent/projects/${projectId}/chapters/${chapterId}/content/stream`,
        body,
        onChunk,
      )
      return {
        project_id: projectId,
        chapter_id: chapterId,
        expected_words: result.meta.expected_words,
        plan: result.meta.plan,
        content: result.content,
        citations: result.meta.citations || [],
      }
    }
    const task = await request<{ job_id: string }>(
      `/api/agent/projects/${projectId}/chapters/${chapterId}/content/jobs`,
      { method: 'POST', body: JSON.stringify(body) },
    )
    let lastContent = ''
    for (let attempt = 0; attempt < 900; attempt += 1) {
      const status = await request<{
        status: string
        progress: number
        content?: string
        plan?: ChapterPlan
        citations?: KnowledgeCitation[]
        expected_words?: number
        error?: string
      }>(`/api/agent/chapter-content/jobs/${task.job_id}`)
      const nextContent = status.content || ''
      if (nextContent.length > lastContent.length) {
        onChunk?.(nextContent.slice(lastContent.length))
        lastContent = nextContent
      }
      if (status.status === 'completed')
        return {
          project_id: projectId,
          chapter_id: chapterId,
          expected_words: status.expected_words || plan.expected_words,
          plan: status.plan || plan,
          content: nextContent,
          citations: status.citations || [],
        }
      if (status.status === 'failed') throw new ApiError(status.error || '章节生成失败，请稍后重试')
      if (status.status === 'cancelled') throw new ApiError('生成任务已取消，可在生成历史中重新生成')
      await new Promise(resolve => window.setTimeout(resolve, 800))
    }
    throw new ApiError('章节生成等待超时，请稍后查看或重试')
  },
  generateChapterMemory: (projectId: number, chapterId: number, userIdea = '') =>
    request<{ project_id: number; chapter_id: number; summary: string; memory: ChapterMemory }>(
      `/api/agent/projects/${projectId}/chapters/${chapterId}/memory`,
      {
        method: 'POST',
        body: JSON.stringify({ user_idea: userIdea }),
      },
    ),
  listChapterContentJobs: (projectId?: number, chapterId?: number, limit = 50) => {
    const query = new URLSearchParams({ limit: String(limit) })
    if (projectId !== undefined) query.set('project_id', String(projectId))
    if (chapterId !== undefined) query.set('chapter_id', String(chapterId))
    return request<GenerationJob[]>(`/api/agent/chapter-content/jobs?${query.toString()}`)
  },
  cancelChapterContentJob: (jobId: string) =>
    request<{ job_id: string; status: string }>(`/api/agent/chapter-content/jobs/${jobId}/cancel`, { method: 'POST' }),
  retryChapterContentJob: (jobId: string) =>
    request<{ job_id: string; status: string; source_job_id?: string }>(
      `/api/agent/chapter-content/jobs/${jobId}/retry`,
      { method: 'POST' },
    ),
  getChapter: (projectId: number, chapterId: number) =>
    request<Chapter>(`/api/project/${projectId}/chapters/${chapterId}`),
  updateProject: (
    projectId: number,
    payload: {
      projectname: string
      introduction: string
      project_type: string
      cover_url: string | null
      status: '连载中' | '完结' | '断更'
    },
  ) => request<Project>(`/api/project/${projectId}`, { method: 'PUT', body: JSON.stringify(payload) }),
  createChapter: (projectId: number, payload: { chapter_number: number; chaptername: string; content?: string }) =>
    request<Chapter>(`/api/project/${projectId}/chapters`, { method: 'POST', body: JSON.stringify(payload) }),
  updateChapter: (
    projectId: number,
    chapterId: number,
    payload: {
      chapter_number: number
      chaptername: string
      content?: string
      plan?: ChapterPlan | null
      summary?: string | null
      memory?: ChapterMemory | null
    },
  ) =>
    request<Chapter>(`/api/project/${projectId}/chapters/${chapterId}`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),
  getChapterVersions: (projectId: number, chapterId: number, limit = 50) =>
    request<ChapterVersion[]>(`/api/project/${projectId}/chapters/${chapterId}/versions?limit=${limit}`),
  restoreChapterVersion: (projectId: number, chapterId: number, versionId: number) =>
    request<Chapter>(`/api/project/${projectId}/chapters/${chapterId}/versions/${versionId}/restore`, {
      method: 'POST',
    }),
  getRecycledProjects: () => request<Project[]>('/api/recycle-bin/projects'),
  getRecycledChapters: () => request<RecycledChapter[]>('/api/recycle-bin/chapters'),
  getRecycledKnowledgeBases: () => request<KnowledgeBase[]>('/api/recycle-bin/knowledge-bases'),
  getRecycledInspirations: () => request<Inspiration[]>('/api/recycle-bin/inspirations'),
  recycleProject: (projectId: number) =>
    request<Project>(`/api/recycle-bin/projects/${projectId}/trash`, { method: 'POST' }),
  restoreProject: (projectId: number) =>
    request<Project>(`/api/recycle-bin/projects/${projectId}/restore`, { method: 'PUT' }),
  permanentlyDeleteProject: (projectId: number) =>
    request<null>(`/api/recycle-bin/projects/${projectId}`, { method: 'DELETE' }),
  recycleChapter: (chapterId: number) =>
    request<Chapter>(`/api/recycle-bin/chapters/${chapterId}/trash`, { method: 'POST' }),
  restoreChapter: (chapterId: number) =>
    request<Chapter>(`/api/recycle-bin/chapters/${chapterId}/restore`, { method: 'PUT' }),
  permanentlyDeleteChapter: (chapterId: number) =>
    request<null>(`/api/recycle-bin/chapters/${chapterId}`, { method: 'DELETE' }),
  restoreKnowledgeBase: (baseId: number) =>
    request<KnowledgeBase>(`/api/recycle-bin/knowledge-bases/${baseId}/restore`, { method: 'PUT' }),
  permanentlyDeleteKnowledgeBase: (baseId: number) =>
    request<null>(`/api/recycle-bin/knowledge-bases/${baseId}`, { method: 'DELETE' }),
  restoreInspiration: (id: number) =>
    request<Inspiration>(`/api/recycle-bin/inspirations/${id}/restore`, { method: 'PUT' }),
  permanentlyDeleteInspiration: (id: number) =>
    request<null>(`/api/recycle-bin/inspirations/${id}`, { method: 'DELETE' }),
  createProject: (projectname: string, introduction: string, project_type: string) =>
    request<Project>('/api/project/newProject', {
      method: 'POST',
      body: JSON.stringify({ projectname, introduction, project_type }),
    }),
  generateProjectField: (payload: {
    field: 'projectname' | 'introduction' | 'project_type'
    projectname?: string
    introduction?: string
    project_type?: string
  }) =>
    request<{ field: string; value: string }>('/api/agent/project-field', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  refineIdea: (idea: string) =>
    request<{ idea: string; refined_idea: string }>('/api/agent/refine-idea', {
      method: 'POST',
      body: JSON.stringify({ idea }),
    }),
}
