import { cleanup, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { api } from '../api/client'
import type { Chapter, OutlineVolume, Project } from '../types'
import { ProjectDetailPage } from './ProjectDetailPage'

vi.mock('../api/client', () => ({
  api: {
    getProject: vi.fn(),
    getReviewPreferences: vi.fn(),
    getProjectReviewPreferences: vi.fn(),
    updateProjectReviewPreferences: vi.fn(),
    getProjectChapters: vi.fn(),
    getOutlineVolumes: vi.fn(),
    updateProject: vi.fn(),
    updateProjectState: vi.fn(),
    generateProjectCover: vi.fn(),
    generateProjectOutline: vi.fn(),
    updateProjectOutline: vi.fn(),
    createChapter: vi.fn(),
    updateChapter: vi.fn(),
    recycleProject: vi.fn(),
    recycleChapter: vi.fn(),
  },
}))

const project: Project = {
  id: 12,
  projectname: '星河归途',
  introduction: '探险队穿越深空，寻找失落的家园。',
  project_type: '科幻',
  cover_url: 'https://example.com/cover.jpg',
  total_words: 2400,
  expected_words: 1000000,
  chapter_count: 1,
  created_at: '2026-10-17T09:00:00',
  updated_at: '2026-10-17T10:00:00',
  status: '连载中',
  current_state_markdown: '# 当前状态\n\n## 主角状态\n刚刚启程。',
}

const chapter: Chapter = {
  id: 8,
  project_id: project.id,
  chapter_number: 1,
  chaptername: '启航',
  created_at: project.created_at,
  updated_at: project.updated_at,
  is_deleted: false,
}

beforeEach(() => {
  vi.resetAllMocks()
  vi.mocked(api.getProject).mockResolvedValue(project)
  vi.mocked(api.getReviewPreferences).mockResolvedValue({
    enabled: false,
    max_rounds: 3,
    accept_score: 85,
    reviewer_mode: 'shared',
    reviewer_model: null,
    configuration_status: 'shared',
    manual_approval: false,
  })
  vi.mocked(api.getProjectReviewPreferences).mockResolvedValue({})
  vi.mocked(api.updateProjectReviewPreferences).mockResolvedValue({})
  vi.mocked(api.getProjectChapters).mockResolvedValue([chapter])
  vi.mocked(api.getOutlineVolumes).mockResolvedValue([])
  vi.mocked(api.updateProject).mockResolvedValue(project)
  vi.mocked(api.updateProjectState).mockResolvedValue({
    project_id: project.id,
    current_state_markdown: project.current_state_markdown!,
    updated_at: project.updated_at,
  })
  vi.mocked(api.generateProjectCover).mockResolvedValue(project)
  vi.mocked(api.generateProjectOutline).mockResolvedValue({
    project_id: project.id,
    expected_words: 120000,
    outline: '第一卷：星海启程\n第二卷：归途之战',
  })
  vi.mocked(api.updateProjectOutline).mockResolvedValue({
    project_id: project.id,
    outline: '第一卷：星海启程\n第二卷：归途之战',
  })
  vi.mocked(api.createChapter).mockResolvedValue({ ...chapter, id: 9, chapter_number: 2, chaptername: '归途' })
  vi.mocked(api.updateChapter).mockResolvedValue(chapter)
})
afterEach(cleanup)

function renderPage() {
  return render(
    <MemoryRouter initialEntries={[`/projects/${project.id}`]}>
      <Routes>
        <Route path="/projects/:projectId" element={<ProjectDetailPage />} />
        <Route path="/projects/:projectId/outline" element={<h1>大纲详情页</h1>} />
        <Route path="/projects" element={<h1>作品列表</h1>} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('作品详情页', () => {
  it('展示封面、作品信息和章节列表', async () => {
    renderPage()

    expect(await screen.findByRole('heading', { name: '星河归途' })).toBeTruthy()
    expect(screen.getByRole('img', { name: '星河归途封面' }).getAttribute('src')).toBe(project.cover_url)
    expect(screen.getByText(project.introduction!)).toBeTruthy()
    expect(screen.getByText(project.project_type!)).toBeTruthy()
    expect(screen.getByRole('heading', { name: '启航' })).toBeTruthy()
    expect(screen.getByText('章节管理')).toBeTruthy()
  })

  it('作品评审覆盖可以清除并回到账户默认值', async () => {
    vi.mocked(api.getProjectReviewPreferences).mockResolvedValue({
      enabled: true,
      max_rounds: 2,
      accept_score: 90,
      manual_approval: true,
    })
    renderPage()

    await screen.findByRole('heading', { name: '作品评审偏好' })
    const reviewerSwitch = screen.getByLabelText('评论员')
    expect((reviewerSwitch as HTMLSelectElement).value).toBe('on')
    await userEvent.click(screen.getByRole('button', { name: '使用账户默认' }))

    expect(api.updateProjectReviewPreferences).toHaveBeenCalledWith(project.id, {
      enabled: null,
      max_rounds: null,
      accept_score: null,
      manual_approval: null,
    })
    expect((screen.getByLabelText('评论员') as HTMLSelectElement).value).toBe('off')
  })

  it('生成智能封面前要求输入作者名，并把作者名传给后端', async () => {
    const generated = { ...project, cover_url: '/uploads/covers/generated.svg' }
    vi.mocked(api.generateProjectCover).mockResolvedValue(generated)
    renderPage()

    await userEvent.click(await screen.findByRole('button', { name: '编辑作品' }))
    await userEvent.click(screen.getByRole('button', { name: '根据内容生成' }))
    const dialog = screen.getByRole('dialog', { name: '生成智能封面' })
    expect(api.generateProjectCover).not.toHaveBeenCalled()
    await userEvent.type(within(dialog).getByRole('textbox', { name: '作者名' }), '星河作者')
    await userEvent.click(within(dialog).getByRole('button', { name: '确认生成' }))

    expect(api.generateProjectCover).toHaveBeenCalledWith(project.id, '星河作者')
    expect(await screen.findByText('智能封面已生成')).toBeTruthy()
  })

  it('正文进度使用章节统计字数累加，而不是作品缓存值', async () => {
    vi.mocked(api.getProjectChapters).mockResolvedValue([{ ...chapter, content: '正文', word_count: 2 }])
    renderPage()

    expect(await screen.findByText('2 / 1,000,000 字')).toBeTruthy()
  })

  it('按卷分组章节并支持展开收起', async () => {
    const volume: OutlineVolume = {
      id: 101,
      project_id: project.id,
      volume_number: 1,
      name: '星海启程',
      start_chapter: 1,
      end_chapter: 20,
      outline: '离开故乡',
      created_at: project.created_at,
      updated_at: project.updated_at,
    }
    vi.mocked(api.getOutlineVolumes).mockResolvedValue([volume])
    vi.mocked(api.getProjectChapters).mockResolvedValue([
      { ...chapter, volume_id: volume.id },
      { ...chapter, id: 9, chapter_number: 2, chaptername: '远航', volume_id: null },
    ])
    renderPage()

    expect(await screen.findByRole('button', { name: /第1卷.*星海启程/ })).toBeTruthy()
    expect(screen.getByRole('heading', { name: '启航' })).toBeTruthy()
    expect(screen.getByRole('heading', { name: '远航' })).toBeTruthy()

    await userEvent.click(screen.getByRole('button', { name: /第1卷.*星海启程/ }))
    expect(screen.queryByRole('heading', { name: '启航' })).toBeNull()
    expect(screen.getByRole('heading', { name: '远航' })).toBeTruthy()
  })

  it('作品详情只保留进入大纲页的入口，智能生成入口在大纲编辑页', async () => {
    renderPage()
    expect(await screen.findByRole('link', { name: '进入大纲详情' })).toBeTruthy()
    expect(screen.queryByRole('button', { name: '智能生成' })).toBeNull()
  })

  it('展示并允许编辑作品当前状态 Markdown', async () => {
    renderPage()

    const openStateButton = await screen.findByRole('button', { name: '查看当前状态' })
    expect(screen.queryByRole('heading', { name: '当前状态' })).toBeNull()
    expect(document.querySelector('.project-state-preview')).toBeNull()
    await userEvent.click(openStateButton)

    expect(await screen.findByRole('heading', { name: '当前状态' })).toBeTruthy()
    expect(document.querySelector('.project-state-preview')?.textContent).toBe(project.current_state_markdown)
    await userEvent.click(screen.getByRole('button', { name: '收起' }))
    expect(document.querySelector('.project-state-preview')).toBeNull()
    await userEvent.click(screen.getByRole('button', { name: '查看当前状态' }))

    await userEvent.click(screen.getByRole('button', { name: '编辑状态' }))
    const editor = screen.getByRole('textbox', { name: '当前状态 Markdown 文档' })
    await userEvent.clear(editor)
    await userEvent.type(editor, '# 当前状态{enter}{enter}## 世界观{enter}星河帝国')
    await userEvent.click(screen.getByRole('button', { name: '保存状态' }))

    expect(api.updateProjectState).toHaveBeenCalledWith(project.id, '# 当前状态\n\n## 世界观\n星河帝国')
    expect(await screen.findByText('当前状态文档已保存')).toBeTruthy()
  })

  it('章节支持从详情页移入回收站并更新列表', async () => {
    vi.mocked(api.recycleChapter).mockResolvedValue(chapter)
    renderPage()

    await userEvent.click(await screen.findByRole('button', { name: '将启航移入回收站' }))
    const dialog = screen.getByRole('dialog', { name: '移入回收站' })
    await userEvent.click(within(dialog).getByRole('button', { name: '移入回收站' }))

    expect(await screen.findByText('还没有章节')).toBeTruthy()
    expect(api.recycleChapter).toHaveBeenCalledWith(chapter.id)
  })

  it('编辑模式可以保存作品信息', async () => {
    const updated = {
      ...project,
      projectname: '星河新篇',
      introduction: '新的简介',
      project_type: '悬疑',
      cover_url: 'https://example.com/new-cover.jpg',
      status: '完结',
    }
    vi.mocked(api.updateProject).mockResolvedValue(updated)
    renderPage()

    await userEvent.click(await screen.findByRole('button', { name: '编辑作品' }))
    await userEvent.clear(screen.getByLabelText('作品名称'))
    await userEvent.type(screen.getByLabelText('作品名称'), updated.projectname)
    await userEvent.selectOptions(screen.getByLabelText('作品类型'), updated.project_type)
    await userEvent.selectOptions(screen.getByLabelText('作品状态'), updated.status)
    await userEvent.clear(screen.getByLabelText('作品简介'))
    await userEvent.type(screen.getByLabelText('作品简介'), updated.introduction)
    await userEvent.clear(screen.getByLabelText('封面地址'))
    await userEvent.type(screen.getByLabelText('封面地址'), updated.cover_url!)
    await userEvent.click(screen.getByRole('button', { name: '保存修改' }))

    expect(api.updateProject).toHaveBeenCalledWith(project.id, {
      projectname: updated.projectname,
      introduction: updated.introduction,
      project_type: updated.project_type,
      cover_url: updated.cover_url,
      expected_words: updated.expected_words || 1000000,
      status: updated.status,
    })
    expect(await screen.findByText('作品信息已保存')).toBeTruthy()
  })

  it('无需编辑作品即可新增章节，并可单独修改章节', async () => {
    const created = { ...chapter, id: 9, chapter_number: 2, chaptername: '归途' }
    vi.mocked(api.createChapter).mockResolvedValue(created)
    vi.mocked(api.updateChapter).mockResolvedValue({ ...chapter, chaptername: '启航（修订）' })
    renderPage()

    await screen.findByRole('button', { name: '新增章节' })
    await userEvent.click(screen.getByRole('button', { name: '新增章节' }))
    await userEvent.type(screen.getByLabelText('新章节名称'), created.chaptername!)
    await userEvent.click(screen.getAllByRole('button', { name: '保存章节' })[0])
    expect(api.createChapter).toHaveBeenCalledWith(project.id, { chapter_number: 2, chaptername: created.chaptername })

    const chapterRow = screen.getByRole('heading', { name: '启航' }).closest('article')!
    await userEvent.click(within(chapterRow).getByRole('button', { name: '修改' }))
    await userEvent.clear(screen.getByLabelText('启航编号'))
    await userEvent.type(screen.getByLabelText('启航编号'), '1')
    await userEvent.clear(screen.getByLabelText('启航名称'))
    await userEvent.type(screen.getByLabelText('启航名称'), '启航（修订）')
    await userEvent.click(screen.getAllByRole('button', { name: '保存章节' })[0])
    expect(api.updateChapter).toHaveBeenCalledWith(project.id, chapter.id, {
      chapter_number: 1,
      chaptername: '启航（修订）',
      content: '',
    })
    expect(await screen.findByRole('button', { name: '修改' })).toBeTruthy()
  })
})
