import { cleanup, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { api } from '../api/client'
import { AppShell } from '../components/AppShell'
import { DashboardPage } from './DashboardPage'
import { ProjectsPage } from './ProjectsPage'

vi.mock('../api/client', () => ({
  api: { getProjects: vi.fn(), createProject: vi.fn() },
}))
vi.mock('../auth/AuthContext', () => ({
  useAuth: () => ({ user: { username: 'writer', nickname: '创作者' }, logout: vi.fn() }),
}))

beforeEach(() => {
  vi.mocked(api.getProjects).mockReset().mockResolvedValue([])
  vi.mocked(api.createProject).mockReset()
  localStorage.clear()
})
afterEach(cleanup)

describe('新建作品入口', () => {
  it.each([
    ['工作台', '/', '当前暂无作品，快去创建你的第一个作品吧！', 'link'],
    ['作品页', '/projects', '当前暂无作品，快去创建你的第一个作品吧！', 'button'],
  ])('%s 仅保留右上角入口，点击仍能打开新建弹窗', async (_page, path, emptyHeading, role) => {
    const { container } = render(
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route element={<AppShell />}>
            <Route index element={<DashboardPage />} />
            <Route path="projects" element={<ProjectsPage />} />
          </Route>
        </Routes>
      </MemoryRouter>,
    )

    await screen.findByRole('heading', { name: emptyHeading })
    const entry = screen.getByRole(role, { name: '新建作品' })
    expect(screen.getAllByText('新建作品')).toHaveLength(1)
    expect(entry.closest('header')).not.toBeNull()
    const emptyState = container.querySelector<HTMLElement>('.empty-state')!
    expect(within(emptyState).queryByRole('button')).toBeNull()
    expect(within(emptyState).queryByRole('link')).toBeNull()

    await userEvent.click(entry)

    expect(screen.getByRole('heading', { name: '创作者，今天写点什么？' })).toBeTruthy()
    expect(screen.getByRole('dialog', { name: '新建作品' })).toBeTruthy()
    expect(screen.getByRole('button', { name: '创建作品' })).toBeTruthy()
  })

  it('弹窗仅保留作品类型选择，不显示智能生成和草稿功能', async () => {
    render(
      <MemoryRouter initialEntries={['/?create=1']}>
        <Routes>
          <Route element={<AppShell />}>
            <Route index element={<DashboardPage />} />
          </Route>
        </Routes>
      </MemoryRouter>,
    )

    const dialog = await screen.findByRole('dialog', { name: '新建作品' })
    expect(within(dialog).getByRole('combobox', { name: '作品类型' })).toBeTruthy()
    expect(dialog.querySelectorAll('label.field')).toHaveLength(1)
    expect(within(dialog).queryByLabelText('智能生成作品名称')).toBeNull()
    expect(within(dialog).queryByLabelText('智能生成作品简介')).toBeNull()
    expect(within(dialog).queryByLabelText('智能生成作品类型')).toBeNull()
    expect(within(dialog).queryByRole('button', { name: '保存草稿' })).toBeNull()
  })

  it('创建后使用返回的作品 ID 跳转到作品详情页', async () => {
    vi.mocked(api.createProject).mockResolvedValue({
      id: 42,
      projectname: '42',
      introduction: null,
      project_type: '科幻',
      total_words: 0,
      chapter_count: 0,
      created_at: '',
      updated_at: '',
      status: '连载中',
    })
    render(
      <MemoryRouter initialEntries={['/?create=1']}>
        <Routes>
          <Route element={<AppShell />}>
            <Route index element={<DashboardPage />} />
            <Route path="projects/:projectId" element={<h1>作品详情页</h1>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    )

    const dialog = await screen.findByRole('dialog', { name: '新建作品' })
    await userEvent.selectOptions(within(dialog).getByRole('combobox'), '科幻')
    await userEvent.click(within(dialog).getByRole('button', { name: '创建作品' }))

    expect(api.createProject).toHaveBeenCalledWith('科幻')
    expect(await screen.findByRole('heading', { name: '作品详情页' })).toBeTruthy()
  })
})
