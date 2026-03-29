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
    backend: string; ready: boolean; detail: string; setup_command: string | null
  } | null>(null)
  const [showSetup, setShowSetup] = useState(false)

  useEffect(() => {
    api.getAiStatus().then(setStatus).catch(() => {})
    // Poll every 5s while not ready (in case user runs setup-token in terminal)
    const interval = setInterval(() => {
      api.getAiStatus().then((s) => {
        setStatus(s)
        if (s.ready) clearInterval(interval)
      }).catch(() => {})
    }, 5000)
    return () => clearInterval(interval)
  }, [])

  if (!status) return null

  if (status.ready) {
    return (
      <span className="text-xs text-green-600 bg-green-50 px-2 py-1 rounded">
        AI: {status.backend === 'cli' ? 'Claude CLI' : 'API'}
      </span>
    )
  }

  return (
    <div className="flex items-center gap-2">
      <button
        onClick={() => setShowSetup(!showSetup)}
        className="text-xs text-amber-600 bg-amber-50 px-2 py-1 rounded hover:bg-amber-100"
      >
        AI: Not connected
      </button>
      {showSetup && status.setup_command && (
        <div className="absolute right-6 top-12 bg-white border border-gray-200 rounded-lg shadow-lg p-4 z-50 max-w-md">
          <p className="text-sm text-gray-700 mb-2">Run this in your terminal:</p>
          <code className="block bg-gray-50 text-xs p-2 rounded font-mono select-all">
            {status.setup_command}
          </code>
          <p className="text-xs text-gray-500 mt-2">
            This connects to your Claude subscription (one-time setup). The page will update automatically when done.
          </p>
        </div>
      )}
    </div>
  )
}

export function AppLayout() {
  const location = useLocation()
  return (
    <div className="min-h-screen bg-gray-50">
      <header className="border-b border-gray-200 bg-white relative">
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
