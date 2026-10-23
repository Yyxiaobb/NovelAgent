import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { api } from '../api/client'
import type { Chapter, ChapterVersion } from '../types'
import { ChapterDetailPage } from './ChapterDetailPage'

vi.mock('../api/client', () => ({
  api: {
    getChapter: vi.fn(),
    updateChapter: vi.fn(),
    generateChapterContent: vi.fn(),
    generateChapterPlan: vi.fn(),
    generateChapterMemory: vi.fn(),
    listChapterContentJobs: vi.fn(),
    cancelChapterContentJob: vi.fn(),
    retryChapterContentJob: vi.fn(),
    getChapterVersions: vi.fn(),
  },
}))

const chapter: Chapter = {
  id: 8,
  project_id: 12,
  chapter_number: 1,
  chaptername: '启航',
  content: '飞船离开了港口。',
  created_at: '2026-10-17T09:00:00',
  updated_at: '2026-10-17T10:00:00',
  is_deleted: false,
}

beforeEach(() => {
  vi.resetAllMocks()
  vi.mocked(api.getChapter).mockResolvedValue(chapter)
  vi.mocked(api.updateChapter).mockResolvedValue({
    ...chapter,
    chapter_number: 2,
    chaptername: '新启航',
    content: '修订后的内容',
  })
  vi.mocked(api.generateChapterContent).mockResolvedValue({
    project_id: chapter.project_id,
    chapter_id: chapter.id,
    expected_words: 2500,
    plan: { objective: '目标', conflict: '冲突', key_events: '事件', ending_hook: '钩子', expected_words: 2500 },
    content: '智能生成的章节正文',
  })
  vi.mocked(api.generateChapterPlan).mockResolvedValue({
    project_id: chapter.project_id,
    chapter_id: chapter.id,
    plan: { objective: '目标', conflict: '冲突', key_events: '事件', ending_hook: '钩子', expected_words: 2500 },
  })
  vi.mocked(api.listChapterContentJobs).mockResolvedValue([])
  vi.mocked(api.retryChapterContentJob).mockResolvedValue({ job_id: 'job-2', source_job_id: 'job-1', status: 'queued' })
  vi.mocked(api.getChapterVersions).mockResolvedValue([])
  vi.mocked(api.generateChapterMemory).mockResolvedValue({
    project_id: chapter.project_id,
    chapter_id: chapter.id,
    summary: '整理后的摘要',
    memory: { character_state: '状态', setting_changes: '设定', unresolved_threads: '线索', timeline: '时间线' },
  })
})
afterEach(cleanup)

function renderPage(initialEntry = '/projects/12/chapters/8') {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <Routes>
        <Route path="/projects/:projectId/chapters/:chapterId" element={<ChapterDetailPage />} />
        <Route path="/projects/:projectId/chapters/:chapterId/:feature" element={<ChapterDetailPage />} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('章节详情页', () => {
  it('可以编辑编号、名称和内容，保存后退出编辑模式并留在当前页', async () => {
    renderPage()
    expect(await screen.findByRole('heading', { name: '启航' })).toBeTruthy()
    expect(screen.getByText('飞船离开了港口。')).toBeTruthy()
    expect(screen.getByRole('link', { name: '返回作品详情' }).getAttribute('href')).toBe('/projects/12')

    await userEvent.click(screen.getByRole('button', { name: '编辑章节' }))
    await userEvent.clear(screen.getByLabelText('章节编号'))
    await userEvent.type(screen.getByLabelText('章节编号'), '2')
    await userEvent.clear(screen.getByLabelText('章节名称'))
    await userEvent.type(screen.getByLabelText('章节名称'), '新启航')
    await userEvent.clear(screen.getByLabelText('章节内容'))
    await userEvent.type(screen.getByLabelText('章节内容'), '修订后的内容')
    await userEvent.click(screen.getByRole('button', { name: '保存修改' }))

    expect(api.updateChapter).toHaveBeenCalledWith(12, 8, {
      chapter_number: 2,
      chaptername: '新启航',
      content: '修订后的内容',
    })
    expect(await screen.findByRole('button', { name: '编辑章节' })).toBeTruthy()
    expect(screen.getByText('修订后的内容')).toBeTruthy()
  })

  it('保存正文后不等待章节记忆整理完成', async () => {
    let finishMemory!: (value: {
      project_id: number
      chapter_id: number
      summary: string
      memory: { character_state: string; setting_changes: string; unresolved_threads: string; timeline: string }
    }) => void
    vi.mocked(api.generateChapterMemory).mockReturnValue(
      new Promise(resolve => {
        finishMemory = resolve
      }),
    )
    renderPage()
    await screen.findByRole('heading', { name: '启航' })
    await userEvent.click(screen.getByRole('button', { name: '编辑章节' }))
    await userEvent.type(screen.getByLabelText('章节内容'), '新段落')
    await userEvent.click(screen.getByRole('button', { name: '保存修改' }))

    expect(await screen.findByRole('button', { name: '编辑章节' })).toBeTruthy()
    expect(screen.getByRole('status').textContent).toContain('摘要正在整理')
    expect(api.generateChapterMemory).toHaveBeenCalledWith(chapter.project_id, chapter.id)

    finishMemory({
      project_id: chapter.project_id,
      chapter_id: chapter.id,
      summary: '整理后的摘要',
      memory: { character_state: '状态', setting_changes: '设定', unresolved_threads: '线索', timeline: '时间线' },
    })
    expect(await screen.findByText('整理后的摘要')).toBeTruthy()
  })

  it('编辑章节时可智能生成正文并将结果放入编辑框', async () => {
    renderPage()
    await screen.findByRole('heading', { name: '启航' })
    expect(screen.queryByRole('button', { name: '智能生成' })).toBeNull()
    await userEvent.click(screen.getByRole('button', { name: '编辑章节' }))
    await userEvent.type(screen.getByLabelText('本章目标'), '完成启航')
    await userEvent.type(screen.getByLabelText('核心冲突'), '面对未知风险')
    await userEvent.type(screen.getByLabelText('关键情节'), '飞船离港；发现信号')
    await userEvent.type(screen.getByLabelText('结尾钩子'), '信号来自船内')
    await userEvent.clear(screen.getByLabelText('本章规划目标字数'))
    await userEvent.type(screen.getByLabelText('本章规划目标字数'), '2500')
    await userEvent.click(screen.getByRole('button', { name: '按规划生成正文' }))
    expect(screen.queryByLabelText('章节生成目标字数')).toBeNull()
    await userEvent.type(screen.getByLabelText('章节生成想法'), '结尾出现新的线索')
    await userEvent.click(screen.getByRole('button', { name: '生成章节' }))
    expect(api.generateChapterContent).toHaveBeenCalledWith(
      chapter.project_id,
      chapter.id,
      {
        objective: '完成启航',
        conflict: '面对未知风险',
        key_events: '飞船离港；发现信号',
        ending_hook: '信号来自船内',
        expected_words: 2500,
      },
      '结尾出现新的线索',
    )
    expect((screen.getByLabelText('章节内容') as HTMLTextAreaElement).value).toBe('智能生成的章节正文')
    expect(api.updateChapter).not.toHaveBeenCalled()
  })

  it('编辑章节时显示章节规划智能生成入口并将结果填入规划字段', async () => {
    renderPage()
    await screen.findByRole('heading', { name: '启航' })
    await userEvent.click(screen.getByRole('button', { name: '编辑章节' }))
    await userEvent.click(screen.getByRole('button', { name: '智能生成规划' }))
    await userEvent.type(screen.getByLabelText('章节规划想法'), '让主角发现神秘信号')
    await userEvent.click(screen.getByRole('button', { name: '生成规划' }))

    expect(api.generateChapterPlan).toHaveBeenCalledWith(12, 8, 3000, '让主角发现神秘信号')
    expect((screen.getByLabelText('本章目标') as HTMLTextAreaElement).value).toBe('目标')
  })

  it('从章节详情跳转到独立的生成历史页，历史记录可带入章节草稿', async () => {
    vi.mocked(api.listChapterContentJobs).mockResolvedValue([
      {
        job_id: 'job-1',
        project_id: 12,
        chapter_id: 8,
        job_type: 'chapter_content',
        status: 'completed',
        progress: 100,
        content: '历史生成的正文',
        expected_words: 2500,
        plan: { objective: '目标', conflict: '冲突', key_events: '事件', ending_hook: '钩子', expected_words: 2500 },
        error: null,
        created_at: '2026-10-17T09:00:00',
        updated_at: '2026-10-17T09:00:00',
        finished_at: '2026-10-17T09:00:00',
      },
    ])
    renderPage()
    await screen.findByRole('heading', { name: '启航' })
    await userEvent.click(screen.getByRole('link', { name: '生成历史' }))
    expect(await screen.findByRole('heading', { name: '正文生成历史' })).toBeTruthy()
    expect(screen.queryByRole('heading', { name: '启航' })).toBeNull()
    await userEvent.click(screen.getByRole('link', { name: '章节详情' }))
    expect(await screen.findByRole('heading', { name: '启航' })).toBeTruthy()
    await userEvent.click(screen.getByRole('link', { name: '生成历史' }))
    expect(await screen.findByRole('heading', { name: '正文生成历史' })).toBeTruthy()
    await userEvent.click(screen.getByRole('button', { name: '用作章节草稿' }))
    expect(((await screen.findByLabelText('章节内容')) as HTMLTextAreaElement).value).toBe('历史生成的正文')
  })

  it('章节版本通过独立页面展示，不与章节详情并列显示', async () => {
    renderPage('/projects/12/chapters/8/versions')
    expect(await screen.findByRole('heading', { name: '章节版本' })).toBeTruthy()
    expect(screen.queryByRole('heading', { name: '启航' })).toBeNull()
    expect(api.getChapterVersions).toHaveBeenCalledWith(12, 8)
    expect(screen.getByRole('link', { name: '返回作品详情' }).getAttribute('href')).toBe('/projects/12')
  })

  it('可将历史章节版本与当前章节并排对比', async () => {
    const version: ChapterVersion = {
      id: 31,
      chapter_id: chapter.id,
      version_number: 2,
      source: 'manual',
      chapter_number: 1,
      chaptername: '启航',
      content: '飞船仍停在港口。',
      plan: null,
      summary: '旧摘要',
      memory: null,
      created_at: '2026-10-17T09:00:00',
    }
    vi.mocked(api.getChapterVersions).mockResolvedValue([version])
    renderPage('/projects/12/chapters/8/versions')
    await userEvent.click(await screen.findByRole('button', { name: '与当前版本对比' }))
    expect(screen.getByRole('region', { name: '版本对比' })).toBeTruthy()
    expect(screen.getByText('版本 2 与当前章节对比')).toBeTruthy()
    expect(screen.getByText('飞船仍停在港口。')).toBeTruthy()
    expect(screen.getByText('飞船离开了港口。')).toBeTruthy()
    expect(screen.getByText('2 项内容有变化')).toBeTruthy()
  })

  it('生成失败后可从历史页重新创建任务', async () => {
    vi.mocked(api.listChapterContentJobs).mockResolvedValue([
      {
        job_id: 'job-1',
        project_id: 12,
        chapter_id: 8,
        job_type: 'chapter_content',
        status: 'failed',
        progress: 12,
        content: '',
        expected_words: 2500,
        plan: null,
        error: '模型暂时不可用',
        created_at: '2026-10-17T09:00:00',
        updated_at: '2026-10-17T09:00:00',
        finished_at: '2026-10-17T09:01:00',
      },
    ])
    renderPage('/projects/12/chapters/8/history')
    expect(await screen.findByText('模型暂时不可用')).toBeTruthy()
    await userEvent.click(screen.getByRole('button', { name: '重新生成' }))
    expect(api.retryChapterContentJob).toHaveBeenCalledWith('job-1')
    expect((await screen.findByRole('status')).textContent).toContain('已重新创建生成任务，页面会自动更新进度')
  })
})
