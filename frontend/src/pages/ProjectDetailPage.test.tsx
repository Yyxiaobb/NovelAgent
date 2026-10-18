import { cleanup, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { api } from '../api/client'
import type { Chapter, Project } from '../types'
import { ProjectDetailPage } from './ProjectDetailPage'

vi.mock('../api/client', () => ({
  api: {
    getProject: vi.fn(),
    getProjectChapters: vi.fn(),
    updateProject: vi.fn(),
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
  chapter_count: 1,
  created_at: '2026-10-17T09:00:00',
  updated_at: '2026-10-17T10:00:00',
  status: '连载中',
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
  vi.mocked(api.getProjectChapters).mockResolvedValue([chapter])
  vi.mocked(api.updateProject).mockResolvedValue(project)
  vi.mocked(api.generateProjectOutline).mockResolvedValue({ project_id: project.id, expected_words: 120000, outline: '第一卷：星海启程\n第二卷：归途之战' })
  vi.mocked(api.updateProjectOutline).mockResolvedValue({ project_id: project.id, outline: '第一卷：星海启程\n第二卷：归途之战' })
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

  it('作品详情只保留进入大纲页的入口，智能生成入口在大纲编辑页', async () => {
    renderPage()
    expect(await screen.findByRole('link', { name: '进入大纲详情' })).toBeTruthy()
    expect(screen.queryByRole('button', { name: '智能生成' })).toBeNull()
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
    const updated = { ...project, projectname: '星河新篇', introduction: '新的简介', project_type: '悬疑', cover_url: 'https://example.com/new-cover.jpg', status: '完结' }
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
    expect(api.updateChapter).toHaveBeenCalledWith(project.id, chapter.id, { chapter_number: 1, chaptername: '启航（修订）', content: '' })
    expect(await screen.findByRole('button', { name: '修改' })).toBeTruthy()
  })
})
