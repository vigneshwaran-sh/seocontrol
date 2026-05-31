import { Navigate, Outlet } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext'

interface ProtectedRouteProps {
  requiredRole?: 'admin' | 'editor' | 'viewer'
}

export default function ProtectedRoute({ requiredRole }: ProtectedRouteProps) {
  const { user, loading } = useAuth()

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-aurora-wash">
        <div className="flex flex-col items-center gap-3">
          <div className="h-8 w-8 animate-spin rounded-full border-4 border-warm-200 border-t-accent" />
          <p className="text-sm text-warm-500">Loading...</p>
        </div>
      </div>
    )
  }

  if (!user) {
    return <Navigate to="/login" replace />
  }

  if (requiredRole && user.role !== requiredRole) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-aurora-wash">
        <div className="text-center">
          <h1 className="text-2xl font-serif font-bold text-warm-900 mb-2">Access Denied</h1>
          <p className="text-warm-500">You do not have permission to view this page.</p>
        </div>
      </div>
    )
  }

  return <Outlet />
}
