import { cleanup, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { api } from '../api/client'
import { AppShell } from '../components/AppShell'
import { DashboardPage } from './DashboardPage'
import { ProjectsPage } from './ProjectsPage'

vi.mock('../api/client', () => ({
  api: { getProjects: vi.fn(), createProject: vi.fn(), generateProjectField: vi.fn() },
}))
vi.mock('../auth/AuthContext', () => ({
  useAuth: () => ({ user: { username: 'writer', nickname: '创作者' }, logout: vi.fn() }),
}))

beforeEach(() => {
  vi.mocked(api.getProjects).mockReset().mockResolvedValue([])
  vi.mocked(api.createProject).mockReset()
  vi.mocked(api.generateProjectField).mockReset()
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

  it('弹窗提供名称、简介和类型的智能生成按钮', async () => {
    vi.mocked(api.generateProjectField).mockImplementation(async ({ field }) => ({
      field,
      value: field === 'projectname' ? '星河归途' : field === 'introduction' ? '一段由智能体生成的故事简介。' : '科幻',
    }))
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
    expect(within(dialog).getByLabelText('智能生成作品名称')).toBeTruthy()
    expect(within(dialog).getByLabelText('智能生成作品简介')).toBeTruthy()
    expect(within(dialog).getByLabelText('智能生成作品类型')).toBeTruthy()

    await userEvent.click(within(dialog).getByLabelText('智能生成作品名称'))
    await userEvent.click(within(dialog).getByLabelText('智能生成作品简介'))
    await userEvent.click(within(dialog).getByLabelText('智能生成作品类型'))

    expect(await within(dialog).findByDisplayValue('星河归途')).toBeTruthy()
    expect(within(dialog).getByDisplayValue('一段由智能体生成的故事简介。')).toBeTruthy()
    expect(within(dialog).getByDisplayValue('科幻')).toBeTruthy()
    expect(api.generateProjectField).toHaveBeenCalledTimes(3)
  })

  it('将作品类型放在作品简介上方', async () => {
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
    const fields = Array.from(dialog.querySelectorAll('label.field')).map(
      field => field.querySelector(':scope > span:first-child')?.textContent,
    )
    expect(fields).toEqual(['作品名称', '作品类型', '作品简介'])
  })

  it('保存草稿后再次打开会自动恢复，并显示保存状态', async () => {
    const { unmount } = render(
      <MemoryRouter initialEntries={['/?create=1']}>
        <Routes>
          <Route element={<AppShell />}>
            <Route index element={<DashboardPage />} />
          </Route>
        </Routes>
      </MemoryRouter>,
    )

    let dialog = await screen.findByRole('dialog', { name: '新建作品' })
    await userEvent.type(within(dialog).getByPlaceholderText('例如：雾港来信'), '星河归途')
    await userEvent.selectOptions(within(dialog).getByRole('combobox'), '科幻')
    await userEvent.type(
      within(dialog).getByPlaceholderText('简要描述故事背景、主角或核心冲突'),
      '一支探险队在深空寻找失落的家园。',
    )
    await userEvent.click(within(dialog).getByRole('button', { name: '保存草稿' }))
    expect((await within(dialog).findByRole('status')).textContent).toContain('草稿已保存')
    expect(JSON.parse(localStorage.getItem('novel-agent-project-draft:anonymous') || '{}')).toEqual({
      name: '星河归途',
      projectType: '科幻',
      introduction: '一支探险队在深空寻找失落的家园。',
    })

    unmount()
    render(
      <MemoryRouter initialEntries={['/?create=1']}>
        <Routes>
          <Route element={<AppShell />}>
            <Route index element={<DashboardPage />} />
          </Route>
        </Routes>
      </MemoryRouter>,
    )
    dialog = await screen.findByRole('dialog', { name: '新建作品' })
    expect(within(dialog).getByDisplayValue('星河归途')).toBeTruthy()
    expect(within(dialog).getByDisplayValue('科幻')).toBeTruthy()
    expect(within(dialog).getByDisplayValue('一支探险队在深空寻找失落的家园。')).toBeTruthy()
  })
})
