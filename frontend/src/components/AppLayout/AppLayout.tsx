import { useEffect, useState, useRef } from 'react'
import { Outlet, Link, useLocation } from 'react-router-dom'
import { clsx } from 'clsx'
import { api } from '@/api/client'

const NAV_ITEMS = [
  { path: '/', label: 'Projects' },
  { path: '/skills', label: 'Skills' },
  { path: '/leaderboard', label: 'Leaderboard' },
  { path: '/guide', label: 'Guide' },
  { path: '/settings', label: 'Settings' },
]

const BACKENDS = [
  { key: 'api' as const, label: 'API', description: 'Direct Anthropic API' },
  { key: 'cli' as const, label: 'Claude CLI', description: 'Claude subscription via CLI' },
]

function AiStatusBadge() {
  const [status, setStatus] = useState<{
    backend: string; ready: boolean; detail: string; setup_hint: string | null
  } | null>(null)
  const [open, setOpen] = useState(false)
  const [switching, setSwitching] = useState(false)
  const menuRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    api.getAiStatus().then(setStatus).catch(() => {})
    const interval = setInterval(() => {
      api.getAiStatus().then((s) => {
        setStatus(s)
        if (s.ready) clearInterval(interval)
      }).catch(() => {})
    }, 5000)
    return () => clearInterval(interval)
  }, [])

  // Close on outside click
  useEffect(() => {
    if (!open) return
    function handleClick(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [open])

  async function handleSwitch(backend: 'api' | 'cli') {
    if (status?.backend === backend) {
      setOpen(false)
      return
    }
    setSwitching(true)
    try {
      await api.switchAiBackend(backend)
      const newStatus = await api.getAiStatus()
      setStatus(newStatus)
    } catch {
      // silent
    } finally {
      setSwitching(false)
      setOpen(false)
    }
  }

  if (!status) return null

  if (!status.ready) {
    return (
      <Link
        to="/settings"
        className="text-xs text-orange-400 bg-orange-400/10 border border-orange-400/20 px-2 py-1 rounded hover:bg-orange-400/20"
      >
        AI: Not connected — click to set up
      </Link>
    )
  }

  return (
    <div className="relative" ref={menuRef}>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="text-xs text-orange-400 bg-orange-400/10 border border-orange-400/20 px-2 py-1 rounded hover:bg-orange-400/20 flex items-center gap-1"
      >
        AI: {status.backend === 'cli' ? 'Claude CLI' : 'API'}
        <svg className={clsx('h-3 w-3 transition-transform', open && 'rotate-180')} viewBox="0 0 12 12" fill="none">
          <path d="M3 5l3 3 3-3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>

      {open && (
        <div className="absolute right-0 top-full mt-1 w-56 rounded-lg border border-stone-700 bg-stone-900 shadow-lg z-50">
          <div className="px-3 py-2 border-b border-stone-800">
            <span className="text-[10px] font-semibold uppercase tracking-wider text-stone-500">AI Backend</span>
          </div>
          {BACKENDS.map((b) => {
            const isActive = status.backend === b.key
            return (
              <button
                key={b.key}
                type="button"
                onClick={() => void handleSwitch(b.key)}
                disabled={switching}
                className={clsx(
                  'flex w-full items-center justify-between px-3 py-2 text-left hover:bg-stone-800',
                  isActive && 'bg-stone-800',
                )}
              >
                <div>
                  <div className="text-sm font-medium text-stone-100">{b.label}</div>
                  <div className="text-[11px] text-stone-500">{b.description}</div>
                </div>
                {isActive && (
                  <span className="text-orange-400 text-xs font-medium">Active</span>
                )}
              </button>
            )
          })}
          <div className="border-t border-stone-800">
            <Link
              to="/settings"
              onClick={() => setOpen(false)}
              className="block px-3 py-2 text-xs text-stone-500 hover:bg-stone-800 hover:text-stone-300"
            >
              Auth settings...
            </Link>
          </div>
        </div>
      )}
    </div>
  )
}

export function AppLayout() {
  const location = useLocation()
  return (
    <div className="min-h-screen bg-stone-950 text-stone-200">
      <header className="border-b border-stone-800 bg-stone-950 relative">
        <div className="mx-auto max-w-7xl px-6 py-3 flex items-center justify-between">
          <Link to="/" className="text-lg font-semibold text-stone-100">Canopy<span className="text-orange-400">.</span></Link>
          <div className="flex items-center gap-6">
            <nav className="flex gap-1">
              {NAV_ITEMS.map((item) => (
                <Link key={item.path} to={item.path}
                  className={clsx('text-sm font-medium px-3 py-1.5 rounded transition-colors',
                    location.pathname === item.path
                      ? 'text-stone-100 bg-stone-900'
                      : 'text-stone-500 hover:text-stone-300 hover:bg-stone-900/50'
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
