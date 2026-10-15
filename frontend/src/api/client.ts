import type { ApiResponse, AuthData, ProfilePayload, Project, User } from '../types'

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
  if (Array.isArray(body.detail)) return body.detail.map((item) => item.msg).filter(Boolean).join('；')
  return body.message || '请求失败，请稍后重试'
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = localStorage.getItem(TOKEN_KEY)
  const headers = new Headers(options.headers)
  if (options.body) headers.set('Content-Type', 'application/json')
  if (token) headers.set('Authorization', `Bearer ${token}`)

  let response: Response
  try {
    response = await fetch(path, { ...options, headers })
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
  changePassword: (oldPassword: string, newPassword: string) =>
    request<null>('/api/user/password', {
      method: 'PUT',
      body: JSON.stringify({ oldPassword, newPassword }),
    }),
  logout: () => request<null>('/api/user/logout', { method: 'POST' }),
  getProjects: () => request<Project[]>('/api/project/projects'),
  createProject: (projectname: string, introduction: string) =>
    request<Project>('/api/project/newProject', {
      method: 'POST',
      body: JSON.stringify({ projectname, introduction }),
    }),
}
