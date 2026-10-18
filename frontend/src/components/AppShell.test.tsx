import { cleanup, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { AppShell } from './AppShell'

vi.mock('../auth/AuthContext', () => ({
  useAuth: () => ({
    user: { username: 'writer', nickname: '创作者' },
    logout: vi.fn(),
  }),
}))

afterEach(cleanup)

function renderShell(start = '/projects') {
  return render(
    <MemoryRouter initialEntries={[start]}>
      <Routes>
        <Route element={<AppShell />}>
          <Route path="projects" element={<h1>我的作品</h1>} />
          <Route path="recycle-bin" element={<h1>回收站内容</h1>} />
        </Route>
      </Routes>
    </MemoryRouter>,
  )
}

describe('侧边栏回收站入口', () => {
  it('回收站独立放在侧边栏底部、用户信息上方，不出现在主导航中', () => {
    const { container } = renderShell()
    const mainNavigation = screen.getByRole('navigation', { name: '主导航' })
    expect(within(mainNavigation).queryByRole('link', { name: '回收站' })).toBeNull()
    expect(within(mainNavigation).getByRole('link', { name: '设置' })).toBeTruthy()

    const footer = container.querySelector('.sidebar-footer')!
    const recycleLink = within(footer as HTMLElement).getByRole('link', { name: '回收站' })
    const userInfo = footer.querySelector('.sidebar-user')!
    expect(recycleLink.getAttribute('href')).toBe('/recycle-bin')
    expect(recycleLink.compareDocumentPosition(userInfo) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(footer.parentElement?.lastElementChild).toBe(footer)
  })

  it('点击底部入口打开回收站，导航高亮随路由更新', async () => {
    renderShell()
    const footerNavigation = screen.getByRole('navigation', { name: '辅助导航' })
    const link = within(footerNavigation).getByRole('link', { name: '回收站' })
    expect(link.getAttribute('aria-current')).toBeNull()

    await userEvent.click(link)

    expect(screen.getByRole('heading', { name: '回收站内容' })).toBeTruthy()
    expect(link.getAttribute('aria-current')).toBe('page')
    expect(link.classList.contains('active')).toBe(true)
  })

  it('移动端保留可用的回收站入口', async () => {
    renderShell()
    const mobileNavigation = screen.getByRole('navigation', { name: '移动端导航' })
    const link = within(mobileNavigation).getByRole('link', { name: '回收站' })

    await userEvent.click(link)

    expect(screen.getByRole('heading', { name: '回收站内容' })).toBeTruthy()
    expect(link.getAttribute('aria-current')).toBe('page')
  })
})
