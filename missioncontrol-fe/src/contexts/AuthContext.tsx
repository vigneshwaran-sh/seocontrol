import { createContext, useContext, useState, useEffect, useCallback } from 'react'
import type { ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import api from '../lib/api'

export interface User {
  id: string
  email: string
  full_name: string
  role: 'admin' | 'editor' | 'viewer'
  is_active: boolean
  created_at: string
  updated_at: string
}

interface AuthContextType {
  user: User | null
  loading: boolean
  login: (email: string, password: string) => Promise<void>
  logout: () => void
  fetchUser: () => Promise<void>
}

const AuthContext = createContext<AuthContextType | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)
  const navigate = useNavigate()

  const fetchUser = useCallback(async () => {
    try {
      const response = await api.get('/api/auth/me')
      setUser(response.data)
    } catch {
      setUser(null)
      localStorage.removeItem('mc_token')
    }
  }, [])

  useEffect(() => {
    const token = localStorage.getItem('mc_token')
    if (token) {
      fetchUser().finally(() => setLoading(false))
    } else {
      setLoading(false)
    }
  }, [fetchUser])

  const login = async (email: string, password: string) => {
    const response = await api.post('/api/auth/login', { email, password })
    localStorage.setItem('mc_token', response.data.access_token)
    setUser(response.data.user)
  }

  const logout = () => {
    localStorage.removeItem('mc_token')
    setUser(null)
    navigate('/login')
  }

  return (
    <AuthContext.Provider value={{ user, loading, login, logout, fetchUser }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthContextType {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}
