import { useEffect, useState } from 'react'
import { Outlet, Link, useLocation } from 'react-router-dom'
import { clsx } from 'clsx'
import { api } from '@/api/client'

const NAV_ITEMS = [
  { path: '/', label: 'Skills' },
  { path: '/leaderboard', label: 'Leaderboard' },
]

type LoginStep = 'idle' | 'starting' | 'waiting_for_code' | 'submitting' | 'done'

function AiStatusBadge() {
  const [status, setStatus] = useState<{
    backend: string; ready: boolean; logged_in: boolean; detail: string; description: string
  } | null>(null)
  const [loginStep, setLoginStep] = useState<LoginStep>('idle')
  const [loginUrl, setLoginUrl] = useState<string | null>(null)
  const [code, setCode] = useState('')
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.getAiStatus().then(setStatus).catch(() => {})
  }, [])

  if (!status) return null

  if (status.ready) {
    return (
      <span className="text-xs text-green-600 bg-green-50 px-2 py-1 rounded" title={status.detail}>
        AI: {status.backend === 'cli' ? 'Claude CLI' : 'API'}
      </span>
    )
  }

  async function handleStartLogin() {
    setLoginStep('starting')
    setError(null)
    try {
      const result = await api.startAiLogin()
      if (result.url) {
        setLoginUrl(result.url)
        setLoginStep('waiting_for_code')
        window.open(result.url, '_blank')
      } else {
        setError('Could not get login URL')
        setLoginStep('idle')
      }
    } catch {
      setError('Failed to start login')
      setLoginStep('idle')
    }
  }

  async function handleSubmitCode() {
    if (!code.trim()) return
    setLoginStep('submitting')
    setError(null)
    try {
      const result = await api.submitLoginCode(code.trim())
      if (result.success) {
        setLoginStep('done')
        // Refresh status
        const s = await api.getAiStatus()
        setStatus(s)
      } else {
        setError(result.output || 'Login failed. Try again.')
        setLoginStep('waiting_for_code')
      }
    } catch {
      setError('Failed to submit code')
      setLoginStep('waiting_for_code')
    }
  }

  return (
    <div className="flex items-center gap-2">
      <span className="text-xs text-amber-600 bg-amber-50 px-2 py-1 rounded">
        AI: Not connected
      </span>

      {/* Step 1: Start login */}
      {status.backend === 'cli' && loginStep === 'idle' && (
        <button
          onClick={() => void handleStartLogin()}
          className="text-xs text-blue-600 hover:text-blue-800 underline"
        >
          Login
        </button>
      )}

      {loginStep === 'starting' && (
        <span className="text-xs text-gray-500">Opening login...</span>
      )}

      {/* Step 2: Paste auth code */}
      {loginStep === 'waiting_for_code' && (
        <div className="flex items-center gap-1">
          {loginUrl && (
            <a href={loginUrl} target="_blank" rel="noopener noreferrer"
              className="text-xs text-blue-600 hover:text-blue-800 underline">
              Auth page
            </a>
          )}
          <input
            type="text"
            value={code}
            onChange={(e) => setCode(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') void handleSubmitCode() }}
            placeholder="Paste auth code"
            className="text-xs border border-gray-300 rounded px-2 py-0.5 w-48"
            autoFocus
          />
          <button
            onClick={() => void handleSubmitCode()}
            disabled={!code.trim()}
            className="text-xs bg-gray-900 text-white px-2 py-0.5 rounded disabled:opacity-50"
          >
            Submit
          </button>
        </div>
      )}

      {loginStep === 'submitting' && (
        <span className="text-xs text-gray-500">Authenticating...</span>
      )}

      {error && <span className="text-xs text-red-500">{error}</span>}
    </div>
  )
}

export function AppLayout() {
  const location = useLocation()
  return (
    <div className="min-h-screen bg-gray-50">
      <header className="border-b border-gray-200 bg-white">
        <div className="mx-auto max-w-7xl px-6 py-3 flex items-center justify-between">
          <Link to="/" className="text-lg font-semibold text-gray-900">Canopy</Link>
          <div className="flex items-center gap-6">
            <nav className="flex gap-6">
              {NAV_ITEMS.map((item) => (
                <Link key={item.path} to={item.path}
                  className={clsx('text-sm font-medium',
                    location.pathname === item.path ? 'text-gray-900' : 'text-gray-500 hover:text-gray-700'
                  )}>
                  {item.label}
                </Link>
              ))}
            </nav>
            <AiStatusBadge />
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-7xl px-6 py-8"><Outlet /></main>
    </div>
  )
}
