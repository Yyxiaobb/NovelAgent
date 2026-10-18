import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { api, tokenStore } from '../api/client'
import type { ProfilePayload, User } from '../types'

interface AuthContextValue {
  user: User | null
  loading: boolean
  login: (username: string, password: string) => Promise<void>
  register: (username: string, password: string) => Promise<void>
  logout: () => Promise<void>
  updateProfile: (payload: ProfilePayload) => Promise<User>
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!tokenStore.get()) {
      setLoading(false)
      return
    }
    api
      .getProfile()
      .then(setUser)
      .catch(() => tokenStore.clear())
      .finally(() => setLoading(false))
  }, [])

  async function authenticate(mode: 'login' | 'register', username: string, password: string) {
    const result = await api[mode](username, password)
    // New browser sessions use the HttpOnly cookie. Clear an older bearer
    // token so it is not retained after a fresh login.
    tokenStore.clear()
    if (result.token) tokenStore.set(result.token)
    setUser(result.userInfo)
  }

  async function logout() {
    try {
      await api.logout()
    } finally {
      tokenStore.clear()
      setUser(null)
    }
  }

  async function updateProfile(payload: ProfilePayload) {
    const updatedUser = await api.updateProfile(payload)
    setUser(updatedUser)
    return updatedUser
  }

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      loading,
      login: (username, password) => authenticate('login', username, password),
      register: (username, password) => authenticate('register', username, password),
      logout,
      updateProfile,
    }),
    [user, loading],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used within AuthProvider')
  return context
}
