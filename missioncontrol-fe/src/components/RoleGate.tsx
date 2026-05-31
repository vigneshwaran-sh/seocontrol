import type { ReactNode } from 'react'
import { useAuth } from '../contexts/AuthContext'

interface RoleGateProps {
  requiredRole: 'admin' | 'editor' | 'viewer'
  children: ReactNode
}

export default function RoleGate({ requiredRole, children }: RoleGateProps) {
  const { user } = useAuth()

  if (user?.role !== requiredRole) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="text-center">
          <h1 className="text-2xl font-bold text-warm-900 mb-2">Access Denied</h1>
          <p className="text-warm-500">You do not have permission to view this page.</p>
        </div>
      </div>
    )
  }

  return <>{children}</>
}
