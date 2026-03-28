import { useEffect, useState } from 'react'
import { Outlet, Link, useLocation } from 'react-router-dom'
import { clsx } from 'clsx'
import { api } from '@/api/client'

const NAV_ITEMS = [
  { path: '/', label: 'Skills' },
  { path: '/leaderboard', label: 'Leaderboard' },
]

function AiStatusBadge() {
  const [status, setStatus] = useState<{
    backend: string; ready: boolean; logged_in: boolean; detail: string; description: string
  } | null>(null)
  const [loginUrl, setLoginUrl] = useState<string | null>(null)
  const [loggingIn, setLoggingIn] = useState(false)

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

  async function handleLogin() {
    setLoggingIn(true)
    try {
      const result = await api.startAiLogin()
      // Extract URL from output
      const urlMatch = result.output.match(/(https:\/\/claude\.com\/[^\s]+)/)
      if (urlMatch) {
        setLoginUrl(urlMatch[1])
        window.open(urlMatch[1], '_blank')
      }
      // Poll for completion
      const poll = setInterval(async () => {
        const s = await api.getAiStatus()
        setStatus(s)
        if (s.ready) {
          clearInterval(poll)
          setLoginUrl(null)
          setLoggingIn(false)
        }
      }, 3000)
      // Stop polling after 2 minutes
      setTimeout(() => { clearInterval(poll); setLoggingIn(false) }, 120000)
    } catch {
      setLoggingIn(false)
    }
  }

  return (
    <div className="flex items-center gap-2">
      <span className="text-xs text-amber-600 bg-amber-50 px-2 py-1 rounded">
        AI: Not connected
      </span>
      {status.backend === 'cli' && !loginUrl && (
        <button
          onClick={() => void handleLogin()}
          disabled={loggingIn}
          className="text-xs text-blue-600 hover:text-blue-800 underline"
        >
          {loggingIn ? 'Opening login...' : 'Login'}
        </button>
      )}
      {loginUrl && (
        <a href={loginUrl} target="_blank" rel="noopener noreferrer"
          className="text-xs text-blue-600 hover:text-blue-800 underline">
          Complete login &rarr;
        </a>
      )}
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
