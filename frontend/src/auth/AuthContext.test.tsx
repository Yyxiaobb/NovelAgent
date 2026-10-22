import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { AuthProvider, useAuth } from './AuthContext'
import { api, tokenStore } from '../api/client'

vi.mock('../api/client', async () => {
  const actual = await vi.importActual<typeof import('../api/client')>('../api/client')
  return { ...actual, api: { ...actual.api, getProfile: vi.fn() } }
})

function Probe() {
  const { user, loading } = useAuth()
  return <output>{loading ? 'loading' : user?.username || 'signed-out'}</output>
}

describe('AuthProvider', () => {
  beforeEach(() => {
    tokenStore.clear()
    vi.mocked(api.getProfile).mockResolvedValue({
      id: 7,
      username: 'cookie-user',
      nickname: null,
      avatar: null,
      gender: 'unknown',
      bio: null,
      phone: null,
    })
  })

  afterEach(() => {
    vi.clearAllMocks()
    tokenStore.clear()
  })

  it('restores an HttpOnly-cookie session even without a local bearer token', async () => {
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    )

    await waitFor(() => expect(screen.getByText('cookie-user')).toBeTruthy())
    expect(api.getProfile).toHaveBeenCalledOnce()
  })
})
