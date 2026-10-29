import { cleanup, render, screen, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { api } from '../api/client'
import { DashboardPage } from './DashboardPage'

vi.mock('../api/client', () => ({ api: { getProjects: vi.fn() } }))
vi.mock('../auth/AuthContext', () => ({ useAuth: () => ({ user: { username: 'writer', nickname: '创作者' } }) }))

beforeEach(() => {
  vi.mocked(api.getProjects).mockReset().mockResolvedValue([
    {
      id: 12,
      projectname: '雾港来信',
      introduction: '一段侦探故事简介',
      project_type: '悬疑',
      total_words: 1200,
      chapter_count: 3,
      created_at: '2026-10-01T10:00:00',
      updated_at: '2026-10-20T10:00:00',
      status: '连载中',
    },
  ])
})

afterEach(cleanup)

describe('工作台最近作品', () => {
  it('显示紧凑的续写入口，不重复作品管理信息', async () => {
    render(
      <MemoryRouter>
        <DashboardPage />
      </MemoryRouter>,
    )

    const recent = await screen.findByRole('link', { name: '继续创作' })
    const item = recent.closest('article')!

    expect(within(item).getByRole('link', { name: '雾港来信' }).getAttribute('href')).toBe('/projects/12')
    expect(recent.getAttribute('href')).toBe('/projects/12')
    expect(item.querySelector('p')).toBeNull()
    expect(item.querySelector('.project-meta')).toBeNull()
    expect(item.querySelector('.status-badge')).toBeNull()
  })
})
