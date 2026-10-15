import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { api, tokenStore } from './client'

beforeEach(() => {
  tokenStore.set('test-token')
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({ code: 200, data: null }),
  }))
})

afterEach(() => {
  tokenStore.clear()
  vi.unstubAllGlobals()
})

describe('独立回收站 API', () => {
  const routes: Array<[string, () => Promise<unknown>, string, string]> = [
    ['作品章节列表', () => api.getProjectChapters(7), '/api/project/7/chapters', 'GET'],
    ['回收作品列表', api.getRecycledProjects, '/api/recycle-bin/projects', 'GET'],
    ['回收章节列表', api.getRecycledChapters, '/api/recycle-bin/chapters', 'GET'],
    ['回收作品', () => api.recycleProject(7), '/api/recycle-bin/projects/7/trash', 'POST'],
    ['还原作品', () => api.restoreProject(7), '/api/recycle-bin/projects/7/restore', 'PUT'],
    ['彻底删除作品', () => api.permanentlyDeleteProject(7), '/api/recycle-bin/projects/7', 'DELETE'],
    ['回收章节', () => api.recycleChapter(21), '/api/recycle-bin/chapters/21/trash', 'POST'],
    ['还原章节', () => api.restoreChapter(21), '/api/recycle-bin/chapters/21/restore', 'PUT'],
    ['彻底删除章节', () => api.permanentlyDeleteChapter(21), '/api/recycle-bin/chapters/21', 'DELETE'],
  ]

  it.each(routes)('%s 使用对应路由和鉴权', async (_, call, path, method) => {
    await call()
    expect(fetch).toHaveBeenCalledTimes(1)
    const [actualPath, options] = vi.mocked(fetch).mock.calls[0]
    expect(actualPath).toBe(path)
    expect(options?.method || 'GET').toBe(method)
    expect(new Headers(options?.headers).get('Authorization')).toBe('Bearer test-token')
  })

  it('向调用页面传递所属项目仍在回收站的错误', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: false,
      status: 409,
      json: async () => ({ detail: '请先还原所属项目，再还原章节' }),
    } as Response)
    await expect(api.restoreChapter(21)).rejects.toMatchObject({
      status: 409,
      message: '请先还原所属项目，再还原章节',
    })
  })
})
