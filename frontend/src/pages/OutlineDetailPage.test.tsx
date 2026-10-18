import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { api } from '../api/client'
import { OutlineDetailPage } from './OutlineDetailPage'

vi.mock('../api/client', () => ({
  api: { getProjectOutline: vi.fn(), updateProjectOutline: vi.fn(), getProject: vi.fn(), generateProjectOutline: vi.fn(), getOutlineVersions: vi.fn() },
}))

beforeEach(() => {
  vi.resetAllMocks()
  vi.mocked(api.getProjectOutline).mockResolvedValue({ project_id: 12, outline: '旧大纲' })
  vi.mocked(api.getProject).mockResolvedValue({ id: 12, projectname: '星河归途', introduction: '', project_type: '科幻', total_words: 0, chapter_count: 0, created_at: '2026-10-17T09:00:00', updated_at: '2026-10-17T10:00:00', status: '连载中' })
  vi.mocked(api.updateProjectOutline).mockResolvedValue({ project_id: 12, outline: '新大纲' })
  vi.mocked(api.generateProjectOutline).mockResolvedValue({ project_id: 12, expected_words: 150000, outline: '智能生成的大纲' })
  vi.mocked(api.getOutlineVersions).mockResolvedValue([])
})
afterEach(cleanup)

describe('大纲详情页', () => {
  function renderOutline(initialEntry = '/projects/12/outline') {
    return render(<MemoryRouter initialEntries={[initialEntry]}><Routes>
      <Route path="/projects/:projectId/outline" element={<OutlineDetailPage />} />
      <Route path="/projects/:projectId/outline/:feature" element={<OutlineDetailPage />} />
    </Routes></MemoryRouter>)
  }

  it('可以保存大纲并退出编辑模式留在当前页', async () => {
    renderOutline()
    expect(await screen.findByText('旧大纲')).toBeTruthy()
    expect(screen.getByRole('link', { name: '返回作品详情' }).getAttribute('href')).toBe('/projects/12')
    await userEvent.click(screen.getByRole('button', { name: '编辑大纲' }))
    await userEvent.clear(screen.getByLabelText('作品大纲'))
    await userEvent.type(screen.getByLabelText('作品大纲'), '新大纲')
    await userEvent.click(screen.getByRole('button', { name: '保存修改' }))
    expect(api.updateProjectOutline).toHaveBeenCalledWith(12, '新大纲')
    expect(await screen.findByRole('button', { name: '编辑大纲' })).toBeTruthy()
    expect(screen.getByText('新大纲')).toBeTruthy()
  })

  it('仅在编辑状态显示智能生成，并将生成结果放入编辑框供用户保存', async () => {
    renderOutline()
    expect(await screen.findByText('旧大纲')).toBeTruthy()
    expect(screen.queryByRole('button', { name: '智能生成' })).toBeNull()
    await userEvent.click(screen.getByRole('button', { name: '编辑大纲' }))
    await userEvent.click(screen.getByRole('button', { name: '智能生成' }))
    await userEvent.clear(screen.getByLabelText('大纲生成期望字数'))
    await userEvent.type(screen.getByLabelText('大纲生成期望字数'), '150000')
    await userEvent.type(screen.getByLabelText('大纲生成想法'), '双主角，温暖结局')
    await userEvent.click(screen.getByRole('button', { name: '生成大纲' }))
    expect(api.generateProjectOutline).toHaveBeenCalledWith(12, 150000, '双主角，温暖结局')
    expect((screen.getByLabelText('作品大纲') as HTMLTextAreaElement).value).toBe('智能生成的大纲')
    expect(api.updateProjectOutline).not.toHaveBeenCalled()
  })

  it('大纲版本通过独立页面展示，不与大纲编辑器并列显示', async () => {
    renderOutline('/projects/12/outline/versions')
    expect(await screen.findByRole('heading', { name: '大纲版本' })).toBeTruthy()
    expect(screen.queryByLabelText('作品大纲')).toBeNull()
    expect(screen.queryByText('旧大纲')).toBeNull()
    expect(api.getOutlineVersions).toHaveBeenCalledWith(12)
    expect(screen.getByRole('link', { name: '返回作品详情' }).getAttribute('href')).toBe('/projects/12')
    await userEvent.click(screen.getByRole('link', { name: '大纲详情' }))
    expect(await screen.findByText('旧大纲')).toBeTruthy()
  })
})
