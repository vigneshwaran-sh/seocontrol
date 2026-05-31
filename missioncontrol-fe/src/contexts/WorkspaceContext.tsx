import { createContext, useContext, useState, useEffect, useCallback } from 'react'
import type { ReactNode } from 'react'
import { useAuth } from './AuthContext'
import api from '../lib/api'
import type { Org, Space } from '../types'

interface WorkspaceContextType {
  currentOrg: Org | null
  spaces: Space[]
  loading: boolean
  refreshSpaces: () => Promise<void>
}

const WorkspaceContext = createContext<WorkspaceContextType | null>(null)

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth()
  const [currentOrg, setCurrentOrg] = useState<Org | null>(null)
  const [spaces, setSpaces] = useState<Space[]>([])
  const [loading, setLoading] = useState(true)

  const fetchSpaces = useCallback(async (orgId: string) => {
    try {
      const response = await api.get(`/api/orgs/${orgId}/spaces`)
      setSpaces(response.data)
    } catch {
      setSpaces([])
    }
  }, [])

  const refreshSpaces = useCallback(async () => {
    if (currentOrg) {
      await fetchSpaces(currentOrg.id)
    }
  }, [currentOrg, fetchSpaces])

  useEffect(() => {
    if (!user) {
      setCurrentOrg(null)
      setSpaces([])
      setLoading(false)
      return
    }

    const init = async () => {
      try {
        const orgsResponse = await api.get('/api/orgs')
        let org: Org

        if (orgsResponse.data.length > 0) {
          org = orgsResponse.data[0]
        } else {
          const createResponse = await api.post('/api/orgs', { name: 'My Organization' })
          org = createResponse.data
        }

        setCurrentOrg(org)
        await fetchSpaces(org.id)
      } catch {
        // silently handle
      } finally {
        setLoading(false)
      }
    }

    init()
  }, [user, fetchSpaces])

  return (
    <WorkspaceContext.Provider value={{ currentOrg, spaces, loading, refreshSpaces }}>
      {children}
    </WorkspaceContext.Provider>
  )
}

export function useWorkspace(): WorkspaceContextType {
  const context = useContext(WorkspaceContext)
  if (!context) {
    throw new Error('useWorkspace must be used within a WorkspaceProvider')
  }
  return context
}
