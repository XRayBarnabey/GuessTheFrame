import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import { api, setCsrfToken } from '../lib/api'
import type { AuthResponse, User } from '../lib/types'

type AuthContextValue = {
  user: User | null
  loading: boolean
  login: (username: string, password: string) => Promise<void>
  logout: () => Promise<void>
  refresh: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  const loadSession = useCallback(async () => {
    try {
      const result = await api.get<AuthResponse>('/api/auth/me')
      setCsrfToken(result.csrf_token)
      setUser(result.user)
    } catch {
      setCsrfToken(null)
      setUser(null)
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    loadSession().finally(() => {
      if (!cancelled) setLoading(false)
    })
    return () => {
      cancelled = true
    }
  }, [loadSession])

  const login = useCallback(async (username: string, password: string) => {
    const result = await api.post<AuthResponse>('/api/auth/login', {
      username,
      password,
    })
    setCsrfToken(result.csrf_token)
    setUser(result.user)
  }, [])

  const logout = useCallback(async () => {
    try {
      await api.post('/api/auth/logout')
    } finally {
      setCsrfToken(null)
      setUser(null)
    }
  }, [])

  const value = useMemo(
    () => ({ user, loading, login, logout, refresh: loadSession }),
    [user, loading, login, logout, loadSession],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used inside AuthProvider')
  return context
}
