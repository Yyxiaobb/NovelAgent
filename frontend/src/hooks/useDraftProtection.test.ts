import { act, cleanup, renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useDraftProtection } from './useDraftProtection'

const storageKey = 'novel-agent:test:draft'

afterEach(() => {
  cleanup()
  window.localStorage.clear()
  vi.restoreAllMocks()
  vi.useRealTimers()
})

describe('useDraftProtection', () => {
  it('debounces local draft writes until typing pauses', async () => {
    vi.useFakeTimers()
    const { result, rerender } = renderHook(
      ({ text }) => useDraftProtection(storageKey, { text }, { text: 'saved' }, true),
      { initialProps: { text: 'saved' } },
    )

    act(() => rerender({ text: 'unsaved words' }))
    expect(result.current.status).toBe('saving')
    expect(window.localStorage.getItem(storageKey)).toBeNull()

    act(() => vi.advanceTimersByTime(700))
    const stored = JSON.parse(window.localStorage.getItem(storageKey) || '{}')
    expect(stored).toMatchObject({ version: 1, data: { text: 'unsaved words' } })
    expect(typeof stored.savedAt).toBe('string')
    expect(result.current.status).toBe('saved')
  })

  it('offers a stored draft that differs from the server baseline', async () => {
    window.localStorage.setItem(
      storageKey,
      JSON.stringify({ version: 1, savedAt: '2026-10-29T10:00:00.000Z', data: { text: 'local words' } }),
    )
    const { result } = renderHook(() =>
      useDraftProtection(storageKey, { text: 'server words' }, { text: 'server words' }, true),
    )

    await waitFor(() => expect(result.current.recovery?.data.text).toBe('local words'))
    act(() => result.current.discardDraft())
    expect(window.localStorage.getItem(storageKey)).toBeNull()
  })

  it('warns on an in-app link and stages changes before staying', () => {
    vi.spyOn(window, 'confirm').mockReturnValue(false)
    renderHook(() => useDraftProtection(storageKey, { text: 'unsaved words' }, { text: 'saved' }, true))
    const link = document.createElement('a')
    link.href = '/projects/13'
    document.body.append(link)

    const event = new MouseEvent('click', { bubbles: true, cancelable: true, button: 0 })
    const navigated = link.dispatchEvent(event)

    expect(navigated).toBe(false)
    expect(window.confirm).toHaveBeenCalledOnce()
    expect(JSON.parse(window.localStorage.getItem(storageKey) || '{}').data).toEqual({ text: 'unsaved words' })
    link.remove()
  })
})
