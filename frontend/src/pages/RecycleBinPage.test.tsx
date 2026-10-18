import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { api } from '../api/client'
import type { Chapter, Project, RecycledChapter } from '../types'
import { ProjectsPage } from './ProjectsPage'
import { RecycleBinPage } from './RecycleBinPage'

vi.mock('../api/client', () => ({
  api: {
    getProjects: vi.fn(),
    getRecycledProjects: vi.fn(),
    createProject: vi.fn(),
    recycleProject: vi.fn(),
    restoreProject: vi.fn(),
    permanentlyDeleteProject: vi.fn(),
    getProjectChapters: vi.fn(),
    getRecycledChapters: vi.fn(),
    recycleChapter: vi.fn(),
    restoreChapter: vi.fn(),
    permanentlyDeleteChapter: vi.fn(),
  },
}))

const novel: Project = {
  id: 7,
  projectname: '雾港来信',
  introduction: '一封迟到的信',
  total_words: 1200,
  chapter_count: 3,
  created_at: '2026-10-15T09:00:00',
  updated_at: '2026-10-15T10:00:00',
  status: '完结',
}

const chapter: RecycledChapter = {
  id: 21,
  project_id: novel.id,
  chapter_number: 2,
  chaptername: '迟来的信',
  created_at: novel.created_at,
  updated_at: novel.updated_at,
  is_deleted: true,
  projectname: novel.projectname,
  project_status: '完结',
}

function renderPage(start = '/recycle-bin') {
  return render(
    <MemoryRouter initialEntries={[start]}>
      <Routes>
        <Route path="/projects" element={<ProjectsPage />} />
        <Route path="/recycle-bin" element={<RecycleBinPage />} />
      </Routes>
    </MemoryRouter>,
  )
}

function expectText(element: HTMLElement, text: string) {
  expect(element.textContent).toContain(text)
}

beforeEach(() => {
  vi.resetAllMocks()
  vi.mocked(api.getProjects).mockResolvedValue([])
  vi.mocked(api.getRecycledProjects).mockResolvedValue([novel])
  vi.mocked(api.getProjectChapters).mockResolvedValue([])
  vi.mocked(api.getRecycledChapters).mockResolvedValue([])
})

afterEach(cleanup)

describe('回收站页面', () => {
  it('作品页右上角不再重复显示回收站入口', async () => {
    renderPage('/projects')
    await screen.findByRole('heading', { name: '作品集还是空的' })
    const header = screen.getByRole('heading', { name: '我的作品' }).closest('header')!
    expect(within(header).queryByRole('link', { name: '回收站' })).toBeNull()
    expect(within(header).getByRole('button', { name: '新建作品' })).toBeTruthy()
  })

  it('渲染回收站作品、章节统计并搜索简介', async () => {
    renderPage()
    expect(await screen.findByRole('heading', { name: '雾港来信' })).toBeTruthy()
    expect(screen.getByText('回收站', { selector: '.status-badge' })).toBeTruthy()
    expect(screen.getByText('3 章')).toBeTruthy()

    await userEvent.type(screen.getByRole('textbox', { name: '搜索回收站' }), '宇宙飞船')
    expect(screen.getByRole('heading', { name: '没有匹配的作品' })).toBeTruthy()
    expect(screen.getByText('共 0 项')).toBeTruthy()
  })

  it('确认后还原项目并保留原状态，然后从回收站移除该项目', async () => {
    const restored = { ...novel, status: '完结' }
    vi.mocked(api.restoreProject).mockResolvedValue(restored)
    renderPage()

    await userEvent.click(await screen.findByRole('button', { name: '还原雾港来信' }))
    const dialog = screen.getByRole('dialog', { name: '还原作品' })
    expect(within(dialog).getByText(/恢复移入回收站前的状态/)).toBeTruthy()
    await userEvent.click(within(dialog).getByRole('button', { name: '确认还原' }))

    await waitFor(() => expect(api.restoreProject).toHaveBeenCalledWith(novel.id))
    expectText(await screen.findByRole('status'), '已还原')
    expect(screen.queryByRole('heading', { name: '雾港来信' })).toBeNull()
  })

  it('取消彻底删除不调用接口；确认后显示不可恢复提示并移除项目', async () => {
    vi.mocked(api.permanentlyDeleteProject).mockResolvedValue(null)
    const user = userEvent.setup()
    renderPage()

    await user.click(await screen.findByRole('button', { name: '彻底删除雾港来信' }))
    let dialog = screen.getByRole('dialog', { name: '彻底删除作品' })
    expect(within(dialog).getByText(/此操作无法撤销/)).toBeTruthy()
    await user.click(within(dialog).getByRole('button', { name: '取消' }))
    expect(api.permanentlyDeleteProject).not.toHaveBeenCalled()
    expect(await screen.findByRole('heading', { name: '雾港来信' })).toBeTruthy()

    await user.click(screen.getByRole('button', { name: '彻底删除雾港来信' }))
    dialog = screen.getByRole('dialog', { name: '彻底删除作品' })
    await user.click(within(dialog).getByRole('button', { name: '彻底删除' }))
    await waitFor(() => expect(api.permanentlyDeleteProject).toHaveBeenCalledWith(novel.id))
    expect(await screen.findByRole('heading', { name: '没有已删除的作品' })).toBeTruthy()
  })

  it('操作失败时保持项目和对话框，允许重试', async () => {
    vi.mocked(api.restoreProject).mockRejectedValueOnce(new Error('服务暂时不可用')).mockResolvedValueOnce(novel)
    const user = userEvent.setup()
    renderPage()

    await user.click(await screen.findByRole('button', { name: '还原雾港来信' }))
    const dialog = screen.getByRole('dialog', { name: '还原作品' })
    await user.click(within(dialog).getByRole('button', { name: '确认还原' }))
    expectText(await within(dialog).findByRole('alert'), '服务暂时不可用')
    expect(await screen.findByRole('heading', { name: '雾港来信' })).toBeTruthy()

    await user.click(within(dialog).getByRole('button', { name: '确认还原' }))
    expectText(await screen.findByRole('status'), '已还原')
    expect(api.restoreProject).toHaveBeenCalledTimes(2)
  })

  it('请求待处理时锁定确认和取消，避免重复提交', async () => {
    let resolveRestore!: (value: Project) => void
    vi.mocked(api.restoreProject).mockReturnValueOnce(new Promise((resolve) => { resolveRestore = resolve }))
    const user = userEvent.setup()
    renderPage()

    await user.click(await screen.findByRole('button', { name: '还原雾港来信' }))
    const dialog = screen.getByRole('dialog', { name: '还原作品' })
    await user.click(within(dialog).getByRole('button', { name: '确认还原' }))
    expect((within(dialog).getByRole('button', { name: '正在还原…' }) as HTMLButtonElement).disabled).toBe(true)
    expect((within(dialog).getByRole('button', { name: '取消' }) as HTMLButtonElement).disabled).toBe(true)
    expect((screen.getByRole('button', { name: '关闭' }) as HTMLButtonElement).disabled).toBe(true)
    expect(api.restoreProject).toHaveBeenCalledTimes(1)

    resolveRestore(novel)
    expectText(await screen.findByRole('status'), '已还原')
  })

  it('重新加载失败后可重试', async () => {
    vi.mocked(api.getRecycledProjects).mockRejectedValueOnce(new Error('离线'))
    renderPage()
    expectText(await screen.findByRole('alert'), '离线')
    await userEvent.click(screen.getByRole('button', { name: '重新加载' }))
    expect(await screen.findByRole('heading', { name: '雾港来信' })).toBeTruthy()
    expect(api.getRecycledProjects).toHaveBeenCalledTimes(2)
  })

  it('作品移入回收站后可跳转查看回收站项目', async () => {
    const user = userEvent.setup()
    vi.mocked(api.recycleProject).mockResolvedValue({ ...novel, status: '回收站' })
    vi.mocked(api.getProjects).mockResolvedValue([novel])
    renderPage('/projects')

    await user.click(await screen.findByRole('button', { name: '将雾港来信移入回收站' }))
    const dialog = screen.getByRole('dialog', { name: '移入回收站' })
    await user.click(within(dialog).getByRole('button', { name: '移入回收站' }))
    expectText(await screen.findByRole('status'), '已移入回收站')
    expect(screen.queryByRole('heading', { name: '雾港来信' })).toBeNull()

    await user.click(screen.getByRole('link', { name: '查看回收站' }))
    expect(await screen.findByRole('heading', { name: '回收站' })).toBeTruthy()
    expect(await screen.findByRole('heading', { name: '雾港来信' })).toBeTruthy()
  })

  it('只在操作结果成功后更新界面', async () => {
    vi.mocked(api.permanentlyDeleteProject).mockRejectedValueOnce(new Error('删除失败'))
    renderPage()
    await userEvent.click(await screen.findByRole('button', { name: '彻底删除雾港来信' }))
    const dialog = screen.getByRole('dialog', { name: '彻底删除作品' })
    await userEvent.click(within(dialog).getByRole('button', { name: '彻底删除' }))
    expectText(await within(dialog).findByRole('alert'), '删除失败')
    expect(await screen.findByRole('heading', { name: '雾港来信' })).toBeTruthy()
  })

  it('覆盖层外点击可取消操作，但提交期间不会关闭', async () => {
    let resolveRestore!: (value: Project) => void
    vi.mocked(api.restoreProject).mockReturnValueOnce(new Promise((resolve) => { resolveRestore = resolve }))
    const user = userEvent.setup()
    renderPage()
    await user.click(await screen.findByRole('button', { name: '还原雾港来信' }))
    const dialog = screen.getByRole('dialog', { name: '还原作品' })
    fireEvent.mouseDown(dialog.parentElement!)
    expect(screen.queryByRole('dialog')).toBeNull()

    await user.click(screen.getByRole('button', { name: '还原雾港来信' }))
    const pendingDialog = screen.getByRole('dialog', { name: '还原作品' })
    await user.click(within(pendingDialog).getByRole('button', { name: '确认还原' }))
    fireEvent.mouseDown(pendingDialog.parentElement!)
    expect(screen.getByRole('dialog', { name: '还原作品' })).toBeTruthy()
    resolveRestore(novel)
    expectText(await screen.findByRole('status'), '已还原')
  })
})

describe('章节管理与回收站', () => {
  it('可用键盘切换标签，空状态仍关联当前标签页', async () => {
    renderPage()
    const projectsTab = await screen.findByRole('tab', { name: '作品 1' })
    projectsTab.focus()
    await userEvent.keyboard('{ArrowRight}')
    expect(document.activeElement).toBe(screen.getByRole('tab', { name: '章节 0' }))
    expect(screen.getByRole('tabpanel', { name: '章节 0' })).toBeTruthy()
    expect(screen.getByRole('heading', { name: '没有已删除的章节' })).toBeTruthy()
    await userEvent.keyboard('{Home}')
    expect(document.activeElement).toBe(projectsTab)
    expect(screen.getByRole('tabpanel', { name: '作品 1' })).toBeTruthy()
  })

  it('作品中展开章节，确认删除后移入回收站并更新章节统计', async () => {
    const activeChapter = { ...chapter, is_deleted: false }
    vi.mocked(api.getProjects).mockResolvedValue([{ ...novel, chapter_count: 1 }])
    vi.mocked(api.getProjectChapters).mockResolvedValue([activeChapter])
    vi.mocked(api.recycleChapter).mockResolvedValue(chapter)
    renderPage('/projects')

    await userEvent.click(await screen.findByRole('button', { name: '管理章节（1）' }))
    expect(await screen.findByText('迟来的信')).toBeTruthy()
    expect(api.getProjectChapters).toHaveBeenCalledWith(novel.id)
    await userEvent.click(screen.getByRole('button', { name: '将迟来的信移入回收站' }))
    const dialog = screen.getByRole('dialog', { name: '移入回收站' })
    await userEvent.click(within(dialog).getByRole('button', { name: '移入回收站' }))
    expectText(await screen.findByRole('status'), '《迟来的信》已移入回收站')
    expect(api.recycleChapter).toHaveBeenCalledWith(chapter.id)
    expect(screen.queryByRole('button', { name: '将迟来的信移入回收站' })).toBeNull()
    expect(screen.getByRole('button', { name: '管理章节（0）' })).toBeTruthy()
    expect(screen.getByText('0 章')).toBeTruthy()
  })

  it('取消章节删除不调用接口，删除失败时保留章节并支持重试', async () => {
    vi.mocked(api.getProjects).mockResolvedValue([novel])
    vi.mocked(api.getProjectChapters).mockResolvedValue([{ ...chapter, is_deleted: false }])
    vi.mocked(api.recycleChapter).mockRejectedValueOnce(new Error('章节删除失败')).mockResolvedValueOnce(chapter)
    renderPage('/projects')
    await userEvent.click(await screen.findByRole('button', { name: '管理章节（3）' }))
    await userEvent.click(await screen.findByRole('button', { name: '将迟来的信移入回收站' }))
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: '取消' }))
    expect(api.recycleChapter).not.toHaveBeenCalled()
    await userEvent.click(screen.getByRole('button', { name: '将迟来的信移入回收站' }))
    const dialog = screen.getByRole('dialog')
    await userEvent.click(within(dialog).getByRole('button', { name: '移入回收站' }))
    expectText(await within(dialog).findByRole('alert'), '章节删除失败')
    expect(screen.getByRole('button', { name: '将迟来的信移入回收站' })).toBeTruthy()
    await userEvent.click(within(dialog).getByRole('button', { name: '移入回收站' }))
    expectText(await screen.findByRole('status'), '已移入回收站')
    expect(api.recycleChapter).toHaveBeenCalledTimes(2)
  })

  it('章节加载失败可重试', async () => {
    vi.mocked(api.getProjects).mockResolvedValue([novel])
    vi.mocked(api.getProjectChapters).mockRejectedValueOnce(new Error('章节暂时不可用')).mockResolvedValueOnce([chapter])
    renderPage('/projects')
    await userEvent.click(await screen.findByRole('button', { name: '管理章节（3）' }))
    expectText(await screen.findByRole('alert'), '章节暂时不可用')
    await userEvent.click(screen.getByRole('button', { name: '重新加载' }))
    expect(await screen.findByRole('button', { name: '将迟来的信移入回收站' })).toBeTruthy()
    expect(api.getProjectChapters).toHaveBeenCalledTimes(2)
  })

  it('切换作品后忽略旧章节请求结果', async () => {
    let resolveFirst!: (value: Chapter[]) => void
    vi.mocked(api.getProjects).mockResolvedValue([novel, { ...novel, id: 8, projectname: '第二部作品', chapter_count: 1 }])
    vi.mocked(api.getProjectChapters)
      .mockReturnValueOnce(new Promise((resolve) => { resolveFirst = resolve }))
      .mockResolvedValueOnce([{ ...chapter, id: 22, project_id: 8, chaptername: '另一封信' }])
    renderPage('/projects')
    await userEvent.click(await screen.findByRole('button', { name: '管理章节（3）' }))
    await userEvent.click(screen.getByRole('button', { name: '管理章节（1）' }))
    expect(await screen.findByText('另一封信')).toBeTruthy()
    await act(async () => { resolveFirst([chapter]) })
    expect(screen.getByText('另一封信')).toBeTruthy()
    expect(screen.queryByText('迟来的信')).toBeNull()
  })

  it('章节标签页显示所属作品并支持搜索', async () => {
    vi.mocked(api.getRecycledChapters).mockResolvedValue([chapter])
    renderPage()
    await screen.findByRole('button', { name: '还原雾港来信' })
    await userEvent.click(screen.getByRole('tab', { name: '章节 1' }))
    expect(screen.getByRole('heading', { name: '迟来的信' })).toBeTruthy()
    expect(screen.getByText('所属作品：雾港来信')).toBeTruthy()
    const search = screen.getByRole('textbox', { name: '搜索回收站' })
    await userEvent.type(search, '雾港')
    expect(screen.getByRole('heading', { name: '迟来的信' })).toBeTruthy()
    await userEvent.clear(search)
    await userEvent.type(search, '不存在')
    expect(screen.getByRole('heading', { name: '没有匹配的章节' })).toBeTruthy()
  })

  it('还原章节后从回收站移除', async () => {
    vi.mocked(api.getRecycledChapters).mockResolvedValue([chapter])
    vi.mocked(api.restoreChapter).mockResolvedValue({ ...chapter, is_deleted: false })
    renderPage()
    await screen.findByRole('button', { name: '还原雾港来信' })
    await userEvent.click(screen.getByRole('tab', { name: '章节 1' }))
    await userEvent.click(screen.getByRole('button', { name: '还原迟来的信' }))
    const dialog = screen.getByRole('dialog', { name: '还原章节' })
    expect(within(dialog).getByText(/以原有编号/)).toBeTruthy()
    await userEvent.click(within(dialog).getByRole('button', { name: '确认还原' }))
    expectText(await screen.findByRole('status'), '《迟来的信》已还原')
    expect(api.restoreChapter).toHaveBeenCalledWith(chapter.id)
    expect(screen.getByRole('heading', { name: '没有已删除的章节' })).toBeTruthy()
  })

  it('章节彻底删除需要确认，失败时不移除并可重试', async () => {
    vi.mocked(api.getRecycledChapters).mockResolvedValue([chapter])
    vi.mocked(api.permanentlyDeleteChapter).mockRejectedValueOnce(new Error('删除失败')).mockResolvedValueOnce(null)
    renderPage()
    await screen.findByRole('button', { name: '还原雾港来信' })
    await userEvent.click(screen.getByRole('tab', { name: '章节 1' }))
    await userEvent.click(screen.getByRole('button', { name: '彻底删除迟来的信' }))
    let dialog = screen.getByRole('dialog', { name: '彻底删除章节' })
    expect(within(dialog).getByText(/此操作无法撤销/)).toBeTruthy()
    await userEvent.click(within(dialog).getByRole('button', { name: '取消' }))
    expect(api.permanentlyDeleteChapter).not.toHaveBeenCalled()
    await userEvent.click(screen.getByRole('button', { name: '彻底删除迟来的信' }))
    dialog = screen.getByRole('dialog', { name: '彻底删除章节' })
    await userEvent.click(within(dialog).getByRole('button', { name: '彻底删除' }))
    expectText(await within(dialog).findByRole('alert'), '删除失败')
    expect(screen.getByRole('heading', { name: '迟来的信' })).toBeTruthy()
    await userEvent.click(within(dialog).getByRole('button', { name: '彻底删除' }))
    expectText(await screen.findByRole('status'), '《迟来的信》已彻底删除')
    expect(api.permanentlyDeleteChapter).toHaveBeenCalledTimes(2)
  })

  it('所属项目在回收站时禁用章节还原，项目还原后才能单独还原章节', async () => {
    vi.mocked(api.getRecycledChapters).mockResolvedValue([{ ...chapter, project_status: '回收站' }])
    vi.mocked(api.restoreProject).mockResolvedValue(novel)
    renderPage()
    await screen.findByRole('button', { name: '还原雾港来信' })
    await userEvent.click(screen.getByRole('tab', { name: '章节 1' }))
    expect((screen.getByRole('button', { name: '还原迟来的信' }) as HTMLButtonElement).disabled).toBe(true)
    expect(screen.getByText('请先还原所属作品')).toBeTruthy()
    expect(api.restoreChapter).not.toHaveBeenCalled()
    await userEvent.click(screen.getByRole('tab', { name: '作品 1' }))
    await userEvent.click(screen.getByRole('button', { name: '还原雾港来信' }))
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: '确认还原' }))
    await screen.findByRole('status')
    await userEvent.click(screen.getByRole('tab', { name: '章节 1' }))
    expect((screen.getByRole('button', { name: '还原迟来的信' }) as HTMLButtonElement).disabled).toBe(false)
    expect(screen.getByRole('heading', { name: '迟来的信' })).toBeTruthy()
  })

  it('彻底删除作品后同时移除所属回收章节', async () => {
    vi.mocked(api.getRecycledChapters).mockResolvedValue([chapter])
    vi.mocked(api.permanentlyDeleteProject).mockResolvedValue(null)
    renderPage()
    await userEvent.click(await screen.findByRole('button', { name: '彻底删除雾港来信' }))
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: '彻底删除' }))
    await screen.findByRole('status')
    await userEvent.click(screen.getByRole('tab', { name: '章节 0' }))
    expect(screen.getByRole('heading', { name: '没有已删除的章节' })).toBeTruthy()
  })

  it('章节还原期间禁止取消和重复提交', async () => {
    let resolveRestore!: (value: Chapter) => void
    vi.mocked(api.getRecycledChapters).mockResolvedValue([chapter])
    vi.mocked(api.restoreChapter).mockReturnValueOnce(new Promise((resolve) => { resolveRestore = resolve }))
    renderPage()
    await screen.findByRole('button', { name: '还原雾港来信' })
    await userEvent.click(screen.getByRole('tab', { name: '章节 1' }))
    await userEvent.click(screen.getByRole('button', { name: '还原迟来的信' }))
    const dialog = screen.getByRole('dialog', { name: '还原章节' })
    await userEvent.click(within(dialog).getByRole('button', { name: '确认还原' }))
    expect((within(dialog).getByRole('button', { name: '正在还原…' }) as HTMLButtonElement).disabled).toBe(true)
    expect((within(dialog).getByRole('button', { name: '取消' }) as HTMLButtonElement).disabled).toBe(true)
    fireEvent.mouseDown(dialog.parentElement!)
    expect(screen.getByRole('dialog')).toBeTruthy()
    expect(api.restoreChapter).toHaveBeenCalledTimes(1)
    await act(async () => { resolveRestore(chapter) })
    expectText(await screen.findByRole('status'), '已还原')
  })
})
