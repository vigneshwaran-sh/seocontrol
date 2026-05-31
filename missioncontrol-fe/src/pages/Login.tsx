import { useState, useEffect } from 'react'
import type { FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext'
import { Rocket } from 'lucide-react'

export default function Login() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const { user, loading, login } = useAuth()
  const navigate = useNavigate()

  useEffect(() => {
    if (!loading && user) {
      navigate('/', { replace: true })
    }
  }, [user, loading, navigate])

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setError('')
    setSubmitting(true)

    try {
      await login(email, password)
      navigate('/', { replace: true })
    } catch (err: unknown) {
      if (err && typeof err === 'object' && 'response' in err) {
        const axiosErr = err as { response?: { data?: { detail?: string } } }
        setError(axiosErr.response?.data?.detail || 'Invalid email or password')
      } else {
        setError('Unable to connect. Please try again.')
      }
    } finally {
      setSubmitting(false)
    }
  }

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-aurora-wash">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-warm-200 border-t-accent" />
      </div>
    )
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-aurora-wash">
      <div className="w-full max-w-sm mx-4">
        {/* App name */}
        <div className="text-center mb-8">
          <div className="flex items-center justify-center gap-2.5 mb-3">
            <div className="h-10 w-10 bg-lumen rounded-xl flex items-center justify-center">
              <Rocket className="h-5 w-5 text-white" />
            </div>
          </div>
          <h1 className="text-3xl font-serif font-bold text-warm-900">MissionControl</h1>
          <p className="mt-2 text-sm text-warm-500">Sign in to your account</p>
        </div>

        {/* Card */}
        <div className="bg-card rounded-xl shadow-e2 p-6">
          {/* Error */}
          {error && (
            <div className="mb-4 p-3 bg-danger-light border border-danger/20 text-danger text-sm rounded-lg">
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label htmlFor="email" className="block text-sm font-medium text-warm-700 mb-1">
                Email
              </label>
              <input
                id="email"
                type="email"
                required
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full px-3 py-2 bg-surface-sunk border-0 rounded-lg text-sm text-warm-900 focus:outline-none focus:ring-2 focus:ring-accent/20"
                placeholder="you@example.com"
              />
            </div>

            <div>
              <label htmlFor="password" className="block text-sm font-medium text-warm-700 mb-1">
                Password
              </label>
              <input
                id="password"
                type="password"
                required
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full px-3 py-2 bg-surface-sunk border-0 rounded-lg text-sm text-warm-900 focus:outline-none focus:ring-2 focus:ring-accent/20"
                placeholder="Enter your password"
              />
            </div>

            <button
              type="submit"
              disabled={submitting}
              className="w-full py-2.5 px-4 text-sm font-medium text-white bg-lumen rounded-lg focus:outline-none focus:ring-2 focus:ring-accent/30 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {submitting ? (
                <span className="flex items-center justify-center gap-2">
                  <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white" />
                  Signing in...
                </span>
              ) : (
                'Sign In'
              )}
            </button>
          </form>
        </div>
      </div>
    </div>
  )
}
