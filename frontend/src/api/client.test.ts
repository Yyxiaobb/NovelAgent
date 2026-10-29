import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { api, tokenStore } from './client'

beforeEach(() => {
  tokenStore.set('test-token')
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ code: 200, data: null }),
    }),
  )
})

afterEach(() => {
  tokenStore.clear()
  vi.unstubAllGlobals()
})

describe('独立回收站 API', () => {
  const routes: Array<[string, () => Promise<unknown>, string, string]> = [
    ['作品章节列表', () => api.getProjectChapters(7), '/api/project/7/chapters', 'GET'],
    ['回收作品列表', api.getRecycledProjects, '/api/recycle-bin/projects', 'GET'],
    ['清空回收作品', api.permanentlyDeleteAllProjects, '/api/recycle-bin/projects/clear', 'DELETE'],
    ['回收章节列表', api.getRecycledChapters, '/api/recycle-bin/chapters', 'GET'],
    ['清空回收章节', api.permanentlyDeleteAllChapters, '/api/recycle-bin/chapters/clear', 'DELETE'],
    ['清空回收卷纲', api.permanentlyDeleteAllOutlineVolumes, '/api/recycle-bin/outline-volumes/clear', 'DELETE'],
    ['清空回收知识库', api.permanentlyDeleteAllKnowledgeBases, '/api/recycle-bin/knowledge-bases/clear', 'DELETE'],
    ['清空回收灵感', api.permanentlyDeleteAllInspirations, '/api/recycle-bin/inspirations/clear', 'DELETE'],
    ['获取卷纲版本', () => api.getOutlineVolumeVersions(12), '/api/project/12/outline/volume-versions?limit=100', 'GET'],
    ['获取滚动细纲版本', () => api.getRollingOutlineVersions(12), '/api/project/12/outline/rolling-versions?limit=100', 'GET'],
    ['恢复卷纲版本', () => api.restoreOutlineVolumeVersion(12, 4), '/api/project/12/outline/volume-versions/4/restore', 'POST'],
    ['恢复滚动细纲版本', () => api.restoreRollingOutlineVersion(12, 5), '/api/project/12/outline/rolling-versions/5/restore', 'POST'],
    ['回收卷纲列表', api.getRecycledOutlineVolumes, '/api/recycle-bin/outline-volumes', 'GET'],
    ['回收作品', () => api.recycleProject(7), '/api/recycle-bin/projects/7/trash', 'POST'],
    ['还原作品', () => api.restoreProject(7), '/api/recycle-bin/projects/7/restore', 'PUT'],
    ['彻底删除作品', () => api.permanentlyDeleteProject(7), '/api/recycle-bin/projects/7', 'DELETE'],
    ['回收章节', () => api.recycleChapter(21), '/api/recycle-bin/chapters/21/trash', 'POST'],
    ['还原章节', () => api.restoreChapter(21), '/api/recycle-bin/chapters/21/restore', 'PUT'],
    ['彻底删除章节', () => api.permanentlyDeleteChapter(21), '/api/recycle-bin/chapters/21', 'DELETE'],
    ['还原卷纲', () => api.restoreOutlineVolume(31), '/api/recycle-bin/outline-volumes/31/restore', 'PUT'],
    ['彻底删除卷纲', () => api.permanentlyDeleteOutlineVolume(31), '/api/recycle-bin/outline-volumes/31', 'DELETE'],
    ['批量生成滚动细纲', () => api.generateRollingChapterPlans(12, [1, 2, 3, 4, 5]), '/api/agent/projects/12/chapters/rolling-plan', 'POST'],
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

  it('智能生成卷纲和滚动细纲不要求前端提交名称', async () => {
    await api.generateOutlineVolume(12, 7, '突出卷末反转', [3])
    let [, volumeOptions] = vi.mocked(fetch).mock.calls[0]
    expect(JSON.parse(String(volumeOptions?.body))).toEqual({ user_idea: '突出卷末反转', knowledge_base_ids: [3] })

    vi.mocked(fetch).mockClear()
    await api.generateRollingChapterPlans(12, [8], 3000, '', [], [1, 2, 3])
    const [, rollingOptions] = vi.mocked(fetch).mock.calls[0]
    expect(JSON.parse(String(rollingOptions?.body))).toEqual({
      chapter_ids: [8],
      chapter_numbers: [1, 2, 3],
      expected_words: 3000,
      user_idea: '',
      knowledge_base_ids: [],
    })
  })
})
