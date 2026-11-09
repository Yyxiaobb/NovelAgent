import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { api } from '../api/client'
import { OutlineDetailPage } from './OutlineDetailPage'

vi.mock('../api/client', () => ({
  api: {
    getProjectOutline: vi.fn(),
    updateProjectOutline: vi.fn(),
    getProject: vi.fn(),
    getInspirations: vi.fn(),
    generateProjectOutline: vi.fn(),
    generateProjectOutlineStream: vi.fn(),
    getOutlineVersions: vi.fn(),
    restoreOutlineVersion: vi.fn(),
    getOutlineVolumeVersions: vi.fn(),
    restoreOutlineVolumeVersion: vi.fn(),
    getRollingOutlineVersions: vi.fn(),
    restoreRollingOutlineVersion: vi.fn(),
    getOutlineVolumes: vi.fn(),
    getProjectChapters: vi.fn(),
    createChapter: vi.fn(),
    generateChapterPlan: vi.fn(),
    generateRollingChapterPlans: vi.fn(),
    updateChapter: vi.fn(),
    createOutlineVolume: vi.fn(),
    updateOutlineVolume: vi.fn(),
    deleteOutlineVolume: vi.fn(),
    generateOutlineVolumePlan: vi.fn(),
  },
}))

beforeEach(() => {
  vi.resetAllMocks()
  window.localStorage.clear()
  vi.mocked(api.getProjectOutline).mockResolvedValue({ project_id: 12, outline: '旧大纲' })
  vi.mocked(api.getProject).mockResolvedValue({
    id: 12,
    projectname: '星河归途',
    introduction: '',
    project_type: '科幻',
    total_words: 0,
    chapter_count: 0,
    created_at: '2026-10-17T09:00:00',
    updated_at: '2026-10-17T10:00:00',
    status: '连载中',
    expected_words: 150000,
  })
  vi.mocked(api.getInspirations).mockResolvedValue([])
  vi.mocked(api.updateProjectOutline).mockResolvedValue({ project_id: 12, outline: '新大纲' })
  vi.mocked(api.generateProjectOutlineStream).mockImplementation(
    async (_id, expected_words, _idea, _knowledgeIds, _inspirationIds, onChunk) => {
      onChunk?.('智能')
      onChunk?.('生成的大纲')
      return { project_id: 12, expected_words }
    },
  )
  vi.mocked(api.getOutlineVersions).mockResolvedValue([])
  vi.mocked(api.restoreOutlineVersion).mockResolvedValue({ project_id: 12, outline: '恢复的大纲' })
  vi.mocked(api.getOutlineVolumeVersions).mockResolvedValue([])
  vi.mocked(api.restoreOutlineVolumeVersion).mockResolvedValue({
    id: 21, project_id: 12, volume_number: 1, name: '第一卷',
    start_chapter: 1, end_chapter: 80, outline: '卷纲', created_at: '2026-10-17T09:00:00',
    updated_at: '2026-10-17T10:00:00',
  })
  vi.mocked(api.getRollingOutlineVersions).mockResolvedValue([])
  vi.mocked(api.restoreRollingOutlineVersion).mockResolvedValue({
    id: 31, project_id: 12, chapter_number: 1, chaptername: '启程', content: null, plan: null,
    summary: null, memory: null, created_at: '2026-10-17T09:00:00', updated_at: '2026-10-17T10:00:00', is_deleted: false,
  })
  vi.mocked(api.getOutlineVolumes).mockResolvedValue([])
  vi.mocked(api.getProjectChapters).mockResolvedValue([])
  vi.mocked(api.createChapter).mockImplementation(async (_projectId, payload) => ({
    id: 100 + payload.chapter_number,
    project_id: 12,
    chapter_number: payload.chapter_number,
    chaptername: payload.chaptername,
    content: null,
    plan: null,
    summary: null,
    memory: null,
    created_at: '2026-10-17T09:00:00',
    updated_at: '2026-10-17T10:00:00',
    is_deleted: false,
  }))
  vi.mocked(api.generateChapterPlan).mockImplementation(async (_projectId, chapterId, expectedWords) => ({
    project_id: 12,
    chapter_id: chapterId,
    plan: {
      objective: `目标${chapterId}`,
      conflict: '冲突',
      key_events: '事件',
      ending_hook: '钩子',
      expected_words: expectedWords || 3000,
    },
  }))
  vi.mocked(api.generateRollingChapterPlans).mockImplementation(async (_projectId, chapterIds) => ({
    project_id: 12,
    plans: chapterIds.map((chapterId, index) => ({
      chapter_id: chapterId,
      chapter_number: index + 1,
      chapter_name: `第${index + 1}章`,
      plan: {
        objective: `目标${chapterId}`,
        conflict: '冲突',
        key_events: '事件',
        ending_hook: '钩子',
        expected_words: 3000,
      },
    })),
  }))
  vi.mocked(api.updateChapter).mockImplementation(async (_projectId, chapterId, payload) => ({
    id: chapterId,
    project_id: 12,
    chapter_number: payload.chapter_number,
    chaptername: payload.chaptername,
    content: payload.content || null,
    plan: payload.plan || null,
    summary: null,
    memory: null,
    created_at: '2026-10-17T09:00:00',
    updated_at: '2026-10-17T10:00:00',
    is_deleted: false,
  }))
  vi.mocked(api.generateOutlineVolumePlan).mockResolvedValue({
    project_id: 12,
    expected_words: 150000,
    volumes: [
      {
        id: 21,
        project_id: 12,
        volume_number: 1,
        name: '第一卷：星港启程',
        start_chapter: 1,
        end_chapter: 50,
        outline: '主角离开星港，发现贯穿全书的异常信号。',
        created_at: '2026-10-17T09:00:00',
        updated_at: '2026-10-17T10:00:00',
      },
    ],
  })
})
afterEach(cleanup)

describe('大纲详情页', () => {
  function renderOutline(initialEntry = '/projects/12/outline') {
    return render(
      <MemoryRouter initialEntries={[initialEntry]}>
        <Routes>
          <Route path="/projects/:projectId/outline" element={<OutlineDetailPage />} />
          <Route path="/projects/:projectId/outline/:feature" element={<OutlineDetailPage />} />
        </Routes>
      </MemoryRouter>,
    )
  }

  it('可以保存大纲并退出编辑模式留在当前页', async () => {
    renderOutline()
    expect(await screen.findByText('旧大纲')).toBeTruthy()
    expect(screen.getByRole('link', { name: '返回作品详情' }).getAttribute('href')).toBe('/projects/12')
    await userEvent.click(screen.getByRole('button', { name: '编辑总纲' }))
    await userEvent.clear(screen.getByLabelText('作品目标字数'))
    await userEvent.type(screen.getByLabelText('作品目标字数'), '180000')
    await userEvent.clear(screen.getByLabelText('作品大纲'))
    await userEvent.type(screen.getByLabelText('作品大纲'), '新大纲')
    await userEvent.click(screen.getByRole('button', { name: '保存修改' }))
    expect(api.updateProjectOutline).toHaveBeenCalledWith(12, '新大纲', 180000)
    expect(await screen.findByRole('button', { name: '编辑总纲' })).toBeTruthy()
    expect(screen.getByText('新大纲')).toBeTruthy()
  })

  it('重新打开大纲页时可以恢复并保存自动暂存的总纲', async () => {
    window.localStorage.setItem(
      'novel-agent:draft:outline:12',
      JSON.stringify({
        version: 1,
        savedAt: '2026-10-29T10:00:00.000Z',
        data: { outline: '恢复的总纲草稿', expectedWords: '180000' },
      }),
    )
    renderOutline()

    expect(await screen.findByText('发现未同步到作品的本地草稿')).toBeTruthy()
    await userEvent.click(screen.getByRole('button', { name: '恢复草稿' }))
    expect((screen.getByLabelText('作品大纲') as HTMLTextAreaElement).value).toBe('恢复的总纲草稿')
    expect((screen.getByLabelText('作品目标字数') as HTMLInputElement).value).toBe('180000')
    await userEvent.click(screen.getByRole('button', { name: '保存修改' }))

    expect(api.updateProjectOutline).toHaveBeenCalledWith(12, '恢复的总纲草稿', 180000)
  })

  it('卷纲本地草稿可从恢复提示恢复到编辑器', async () => {
    const volume = {
      id: 2,
      project_id: 12,
      volume_number: 1,
      name: '第一卷',
      start_chapter: 1,
      end_chapter: 80,
      outline: '服务器卷纲',
      created_at: '2026-10-17T09:00:00',
      updated_at: '2026-10-17T10:00:00',
    }
    vi.mocked(api.getOutlineVolumes).mockResolvedValue([volume])
    window.localStorage.setItem(
      'novel-agent:draft:outline-volumes:12',
      JSON.stringify({
        version: 1,
        savedAt: '2026-10-29T10:00:00.000Z',
        data: { volumes: [{ ...volume, outline: '恢复的卷纲草稿' }], newVolumeDraft: null },
      }),
    )
    renderOutline()

    await screen.findByText('旧大纲')
    await userEvent.click(screen.getByRole('tab', { name: '卷纲' }))
    expect(await screen.findByText('发现未同步到作品的本地草稿')).toBeTruthy()
    await userEvent.click(screen.getByRole('button', { name: '恢复草稿' }))
    expect((await screen.findByLabelText('第一卷卷纲'))).toHaveProperty('value', '恢复的卷纲草稿')
    expect(screen.getByLabelText('第一卷卷纲')).toHaveProperty('disabled', false)
  })

  it('编辑目标字数，智能生成使用该字数并将流式结果写入大纲编辑框', async () => {
    renderOutline()
    expect(await screen.findByText('旧大纲')).toBeTruthy()
    expect(screen.queryByRole('button', { name: '智能生成' })).toBeNull()
    await userEvent.click(screen.getByRole('button', { name: '编辑总纲' }))
    expect(screen.getByLabelText('作品目标字数')).toHaveProperty('value', '150000')
    await userEvent.click(screen.getByRole('button', { name: '智能生成' }))
    expect(screen.getByLabelText('大纲生成期望字数')).toHaveProperty('value', '150000')
    await userEvent.type(screen.getByLabelText('大纲生成想法'), '双主角，温暖结局')
    await userEvent.click(screen.getByRole('button', { name: '生成大纲' }))
    expect(api.generateProjectOutlineStream).toHaveBeenCalledWith(
      12,
      150000,
      '双主角，温暖结局',
      [],
      [],
      expect.any(Function),
    )
    expect((screen.getByLabelText('作品大纲') as HTMLTextAreaElement).value).toBe('智能生成的大纲')
    expect(api.updateProjectOutline).not.toHaveBeenCalled()
  })

  it('可以在总纲生成前注入已有灵感', async () => {
    vi.mocked(api.getInspirations).mockResolvedValue([
      {
        id: 7,
        title: '星港灵感',
        content: '主角在星港收到一段来自未来的求救信号。',
        refined_content: null,
        is_deleted: false,
        created_at: '2026-10-17T09:00:00',
        updated_at: '2026-10-17T10:00:00',
      },
    ])
    renderOutline()
    await screen.findByText('旧大纲')
    await userEvent.click(screen.getByRole('button', { name: '编辑总纲' }))
    await userEvent.click(screen.getByRole('button', { name: '智能生成' }))
    await userEvent.click(screen.getByRole('button', { name: /注入已有灵感/ }))
    await userEvent.click(screen.getByRole('checkbox', { name: '星港灵感' }))
    await userEvent.type(screen.getByLabelText('大纲生成想法'), '双主角，温暖结局')
    await userEvent.click(screen.getByRole('button', { name: '生成大纲' }))
    expect(api.generateProjectOutlineStream).toHaveBeenCalledWith(
      12,
      150000,
      '双主角，温暖结局',
      [],
      [7],
      expect.any(Function),
    )
  })

  it('shows the default target and outline character count', async () => {
    vi.mocked(api.getProject).mockResolvedValue({
      id: 12,
      projectname: '星河归途',
      introduction: '',
      project_type: '科幻',
      total_words: 0,
      chapter_count: 0,
      created_at: '2026-10-17T09:00:00',
      updated_at: '2026-10-17T10:00:00',
      status: '连载中',
    })
    renderOutline()
    expect(await screen.findByText('目标字数：1,000,000 字')).toBeTruthy()
    expect(screen.getByText('大纲字数：3')).toBeTruthy()
  })

  it('空总纲提示编辑入口位于右上方', async () => {
    vi.mocked(api.getProjectOutline).mockResolvedValue({ project_id: 12, outline: '' })
    renderOutline()
    expect(await screen.findByText('暂未填写大纲，点击右上方“编辑大纲”开始编写。')).toBeTruthy()
  })

  it('按作品目标字数智能分卷并生成各卷卷纲', async () => {
    renderOutline()
    await screen.findByText('旧大纲')
    await userEvent.click(screen.getByRole('tab', { name: '卷纲' }))
    await userEvent.click(await screen.findByRole('button', { name: '智能分卷' }))

    expect(api.generateOutlineVolumePlan).toHaveBeenCalledWith(12, 150000, false, [])
    expect(await screen.findByRole('heading', { name: '第一卷：星港启程' })).toBeTruthy()
    expect(screen.getByLabelText('第一卷：星港启程卷纲')).toHaveProperty(
      'value',
      '主角离开星港，发现贯穿全书的异常信号。',
    )
  })

  it('新建卷纲先弹窗确认，确认后才提交卷信息', async () => {
    vi.mocked(api.createOutlineVolume).mockResolvedValue({
      id: 41,
      project_id: 12,
      volume_number: 1,
      name: '第一卷',
      start_chapter: null,
      end_chapter: null,
      outline: '',
      created_at: '2026-10-17T09:00:00',
      updated_at: '2026-10-17T10:00:00',
    })
    renderOutline()
    await screen.findByText('旧大纲')
    await userEvent.click(screen.getByRole('tab', { name: '卷纲' }))
    await userEvent.click(await screen.findByRole('button', { name: '新建卷纲' }))
    expect(screen.getByRole('dialog', { name: '新建卷纲' })).toBeTruthy()
    expect(api.createOutlineVolume).not.toHaveBeenCalled()
    await userEvent.click(screen.getByRole('button', { name: '确认创建' }))
    await waitFor(() => expect(api.createOutlineVolume).toHaveBeenCalledWith(12, {
      volume_number: 1,
      name: '第1卷',
      outline: '',
    }))
  })

  it('shows volume outlines and rolling chapter fine outlines in separate tabs', async () => {
    vi.mocked(api.getOutlineVolumes).mockResolvedValue([
      {
        id: 2,
        project_id: 12,
        volume_number: 1,
        name: '第一卷',
        start_chapter: 1,
        end_chapter: 80,
        outline: '主角离开故乡，发现第一条线索。',
        created_at: '2026-10-17T09:00:00',
        updated_at: '2026-10-17T10:00:00',
      },
    ])
    vi.mocked(api.getProjectChapters).mockResolvedValue([
      {
        id: 8,
        project_id: 12,
        chapter_number: 1,
        chaptername: '启航',
        plan: {
          objective: '离开故乡',
          conflict: '遭遇追兵',
          key_events: '发现信号',
          ending_hook: '信号回应',
          expected_words: 3000,
        },
        created_at: '2026-10-17T09:00:00',
        updated_at: '2026-10-17T10:00:00',
        is_deleted: false,
      },
    ])
    renderOutline()
    await screen.findByText('旧大纲')
    await userEvent.click(screen.getByRole('tab', { name: '卷纲' }))
    expect(await screen.findByText('第一卷')).toBeTruthy()
    expect(screen.getByLabelText('第一卷卷纲')).toHaveProperty('value', '主角离开故乡，发现第一条线索。')
    await userEvent.click(screen.getByRole('tab', { name: '滚动细纲' }))
    expect(await screen.findByText('启航')).toBeTruthy()
    expect(screen.getByText('离开故乡')).toBeTruthy()
    expect(screen.getByRole('link', { name: /第1章.*启航/ }).getAttribute('href')).toBe('/projects/12/chapters/8')
  })

  it('已有卷纲默认只读，修改并保存后恢复只读状态', async () => {
    const volume = {
      id: 2,
      project_id: 12,
      volume_number: 1,
      name: '第一卷',
      start_chapter: 1,
      end_chapter: 80,
      outline: '主角离开故乡，发现第一条线索。',
      created_at: '2026-10-17T09:00:00',
      updated_at: '2026-10-17T10:00:00',
    }
    vi.mocked(api.getOutlineVolumes).mockResolvedValue([volume])
    vi.mocked(api.updateOutlineVolume).mockResolvedValue({ ...volume, outline: '修改后的卷纲' })
    renderOutline()
    await screen.findByText('旧大纲')
    await userEvent.click(screen.getByRole('tab', { name: '卷纲' }))
    const outline = (await screen.findByLabelText('第一卷卷纲')) as HTMLTextAreaElement
    expect(outline.disabled).toBe(true)
    expect(screen.queryByRole('button', { name: '智能生成卷纲' })).toBeNull()
    expect(screen.queryByRole('button', { name: '删除' })).toBeNull()
    await userEvent.click(screen.getByRole('button', { name: '修改卷纲' }))
    expect(outline.disabled).toBe(false)
    expect(screen.getByRole('button', { name: '智能生成卷纲' })).toBeTruthy()
    expect(screen.queryByRole('button', { name: '修改卷纲' })).toBeNull()
    expect(screen.getByRole('button', { name: '删除' })).toBeTruthy()
    await userEvent.clear(outline)
    await userEvent.type(outline, '修改后的卷纲')
    await userEvent.click(screen.getByRole('button', { name: '保存卷纲' }))

    expect(api.updateOutlineVolume).toHaveBeenCalledWith(12, 2, {
      volume_number: 1,
      name: '第一卷',
      outline: '修改后的卷纲',
    })
    expect(await screen.findByRole('button', { name: '修改卷纲' })).toBeTruthy()
    expect(screen.queryByRole('button', { name: '智能生成卷纲' })).toBeNull()
    expect(screen.queryByRole('button', { name: '删除' })).toBeNull()
    expect(screen.queryByRole('button', { name: '保存卷纲' })).toBeNull()
    expect(outline.disabled).toBe(true)
  })

  it('大纲版本通过独立页面展示，不与大纲编辑器并列显示', async () => {
    renderOutline('/projects/12/outline/versions')
    expect(await screen.findByRole('heading', { name: '大纲版本' })).toBeTruthy()
    expect(screen.queryByLabelText('作品大纲')).toBeNull()
    expect(screen.queryByText('旧大纲')).toBeNull()
    expect(api.getOutlineVersions).toHaveBeenCalledWith(12)
    expect(screen.getByRole('link', { name: '返回作品详情' }).getAttribute('href')).toBe('/projects/12')
    const detailLink = screen.getByRole('link', { name: '大纲详情' })
    const versionsLink = screen.getByRole('link', { name: '大纲版本' })
    expect(detailLink.classList.contains('active')).toBe(false)
    expect(versionsLink.classList.contains('active')).toBe(true)
    const versionTabs = screen.getByRole('tablist', { name: '大纲版本类型' })
    expect(within(versionTabs).getByRole('tab', { name: '总纲' }).getAttribute('aria-selected')).toBe('true')
    await userEvent.click(within(versionTabs).getByRole('tab', { name: '卷纲' }))
    expect(api.getOutlineVolumeVersions).toHaveBeenCalledWith(12)
    expect(await screen.findByText(/修改、删除或重新生成卷纲后/)).toBeTruthy()
    await userEvent.click(within(versionTabs).getByRole('tab', { name: '滚动细纲' }))
    expect(api.getRollingOutlineVersions).toHaveBeenCalledWith(12)
    expect(await screen.findByText(/修改章节细纲后/)).toBeTruthy()
    await userEvent.click(within(versionTabs).getByRole('tab', { name: '总纲' }))
    await userEvent.click(detailLink)
    expect(await screen.findByText('旧大纲')).toBeTruthy()
    expect(screen.getByRole('link', { name: '大纲详情' }).classList.contains('active')).toBe(true)
    expect(screen.getByRole('link', { name: '大纲版本' }).classList.contains('active')).toBe(false)
  })

  it('智能规划从第一章无细纲处开始补齐五章，并自动新增缺失章节', async () => {
    const initialChapters = [
      {
        id: 1, project_id: 12, chapter_number: 1, chaptername: '第一章', content: null, plan: null,
        summary: null, memory: null, created_at: '2026-10-17T09:00:00', updated_at: '2026-10-17T10:00:00', is_deleted: false,
      },
    ]
    vi.mocked(api.getProjectChapters).mockResolvedValueOnce(initialChapters).mockResolvedValueOnce(initialChapters)
    vi.mocked(api.generateRollingChapterPlans).mockImplementation(async (_id, _chapterIds, expectedWords, _idea, _knowledgeIds, chapterNumbers = []) => ({
      project_id: 12,
      plans: chapterNumbers.map((chapterNumber, index) => ({
        chapter_id: index === 0 ? 1 : -chapterNumber,
        chapter_number: chapterNumber,
        chapter_name: `第${chapterNumber}章`,
        plan: { objective: `目标${chapterNumber}`, conflict: '冲突', key_events: '事件', ending_hook: '钩子', expected_words: expectedWords || 3000 },
      })),
    }))
    renderOutline()
    await screen.findByText('旧大纲')
    await userEvent.click(screen.getByRole('tab', { name: '滚动细纲' }))
    await screen.findByText('第一章')
    await userEvent.click(screen.getByRole('button', { name: '智能规划滚动细纲' }))

    await waitFor(() => expect(api.generateRollingChapterPlans).toHaveBeenCalledTimes(1))
    expect(api.generateRollingChapterPlans).toHaveBeenCalledWith(
      12,
      [1],
      3000,
      '',
      [],
      [1, 2, 3, 4, 5],
    )
    expect(api.createChapter).not.toHaveBeenCalled()
    expect(api.updateChapter).not.toHaveBeenCalled()
    expect((await screen.findByRole('status')).textContent).toContain('已完成')
  })

  it('细纲生成失败时不会创建新的章节', async () => {
    const initialChapters = [
      {
        id: 1, project_id: 12, chapter_number: 1, chaptername: '第一章', content: null, plan: null,
        summary: null, memory: null, created_at: '2026-10-17T09:00:00', updated_at: '2026-10-17T10:00:00', is_deleted: false,
      },
    ]
    vi.mocked(api.getProjectChapters).mockResolvedValueOnce(initialChapters)
    vi.mocked(api.generateRollingChapterPlans).mockRejectedValueOnce(new Error('模型生成失败'))
    renderOutline()
    await screen.findByText('旧大纲')
    await userEvent.click(screen.getByRole('tab', { name: '滚动细纲' }))
    await screen.findByText('第一章')
    await userEvent.click(screen.getByRole('button', { name: '智能规划滚动细纲' }))

    expect((await screen.findByRole('alert')).textContent).toContain('模型生成失败')
    expect(api.createChapter).not.toHaveBeenCalled()
  })
})
