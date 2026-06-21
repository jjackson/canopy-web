import { useEffect, useState, useRef } from 'react'
import { Outlet, Link, useLocation } from 'react-router-dom'
import { clsx } from 'clsx'
import { aiStatus, aiSwitch } from '@/api/ai'
import { useAuth } from '@/auth/AuthProvider'
import { ThemeToggle } from '@/theme/ThemeProvider'

const NAV_ITEMS = [
  { path: '/', label: 'Projects' },
  { path: '/timeline', label: 'Timeline' },
  { path: '/insights', label: 'Insights' },
  { path: '/shareouts', label: 'Shareouts' },
  { path: '/skills', label: 'Skills' },
  { path: '/walkthroughs', label: 'Walkthroughs' },
  { path: '/sessions', label: 'Sessions' },
  { path: '/agents', label: 'Agents' },
  { path: '/ddd', label: 'DDD' },
  { path: '/workspaces', label: 'Workspaces' },
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
    aiStatus().then(setStatus).catch(() => {})
    const interval = setInterval(() => {
      aiStatus().then((s) => {
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
      await aiSwitch(backend)
      const newStatus = await aiStatus()
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
        className="text-xs text-primary bg-primary/10 border border-primary/20 px-2 py-1 rounded hover:bg-primary/20"
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
        className="text-xs text-primary bg-primary/10 border border-primary/20 px-2 py-1 rounded hover:bg-primary/20 flex items-center gap-1"
      >
        AI: {status.backend === 'cli' ? 'Claude CLI' : 'API'}
        <svg className={clsx('h-3 w-3 transition-transform', open && 'rotate-180')} viewBox="0 0 12 12" fill="none">
          <path d="M3 5l3 3 3-3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>

      {open && (
        <div className="absolute right-0 top-full mt-1 w-56 rounded-lg border border-input bg-card shadow-lg z-50">
          <div className="px-3 py-2 border-b border-border">
            <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">AI Backend</span>
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
                  'flex w-full items-center justify-between px-3 py-2 text-left hover:bg-muted',
                  isActive && 'bg-muted',
                )}
              >
                <div>
                  <div className="text-sm font-medium text-foreground">{b.label}</div>
                  <div className="text-[11px] text-muted-foreground">{b.description}</div>
                </div>
                {isActive && (
                  <span className="text-primary text-xs font-medium">Active</span>
                )}
              </button>
            )
          })}
          <div className="border-t border-border">
            <Link
              to="/settings"
              onClick={() => setOpen(false)}
              className="block px-3 py-2 text-xs text-muted-foreground hover:bg-muted hover:text-foreground-secondary"
            >
              Auth settings...
            </Link>
          </div>
        </div>
      )}
    </div>
  )
}

function UserChip() {
  const auth = useAuth()
  const [open, setOpen] = useState(false)
  const menuRef = useRef<HTMLDivElement>(null)

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

  if (auth.status !== 'authenticated') return null

  const csrfToken = (document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/)?.[1] ?? '')
  const initials = (auth.user.name || auth.user.email).slice(0, 1).toUpperCase()

  return (
    <div className="relative" ref={menuRef}>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="flex items-center gap-2 rounded-full border border-border bg-card pl-1 pr-3 py-1 hover:bg-muted"
      >
        {auth.user.avatar_url ? (
          <img src={auth.user.avatar_url} alt="" className="h-6 w-6 rounded-full" />
        ) : (
          <span className="h-6 w-6 rounded-full bg-primary text-white text-xs font-semibold flex items-center justify-center">
            {initials}
          </span>
        )}
        <span className="hidden sm:inline text-xs text-foreground-secondary max-w-[12rem] truncate">{auth.user.email}</span>
      </button>

      {open && (
        <div className="absolute right-0 top-full mt-1 w-56 rounded-lg border border-input bg-card shadow-lg z-50">
          <div className="px-3 py-2 border-b border-border text-xs text-foreground-secondary">
            Signed in as
            <div className="text-foreground-secondary truncate">{auth.user.email}</div>
          </div>
          <form method="post" action="/accounts/logout/">
            <input type="hidden" name="csrfmiddlewaretoken" value={decodeURIComponent(csrfToken)} />
            <button
              type="submit"
              className="w-full text-left px-3 py-2 text-sm text-foreground-secondary hover:bg-muted"
            >
              Sign out
            </button>
          </form>
        </div>
      )}
    </div>
  )
}

export function AppLayout() {
  const location = useLocation()
  const [mobileOpen, setMobileOpen] = useState(false)

  // Collapse the mobile menu whenever the route changes (e.g. tapping a link).
  useEffect(() => {
    setMobileOpen(false)
  }, [location.pathname])

  function navLinkClass(path: string, block: boolean) {
    const isActive =
      location.pathname === path ||
      (path !== '/' && location.pathname.startsWith(path))
    return clsx(
      'text-sm font-medium rounded transition-colors',
      block ? 'block px-3 py-2' : 'px-3 py-1.5',
      isActive
        ? 'text-foreground bg-card'
        : 'text-muted-foreground hover:text-foreground-secondary hover:bg-card/50',
    )
  }

  return (
    <div className="min-h-screen bg-background text-foreground-secondary">
      <header className="border-b border-border bg-background relative">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 py-3 flex items-center justify-between gap-3">
          <Link to="/" className="text-lg font-semibold text-foreground shrink-0">Canopy<span className="text-primary">.</span></Link>
          <div className="flex items-center gap-3 xl:gap-6">
            {/* Full inline nav only once all items fit (~xl); below that it
                overflows the viewport, so we collapse it into the menu below. */}
            <nav className="hidden xl:flex gap-1">
              {NAV_ITEMS.map((item) => (
                <Link key={item.path} to={item.path} className={navLinkClass(item.path, false)}>
                  {item.label}
                </Link>
              ))}
            </nav>
            <ThemeToggle />
            <AiStatusBadge />
            <UserChip />
            <button
              type="button"
              onClick={() => setMobileOpen((o) => !o)}
              aria-label="Toggle navigation menu"
              aria-expanded={mobileOpen}
              className="xl:hidden -mr-1 p-2 rounded text-foreground-secondary hover:text-foreground-secondary hover:bg-card"
            >
              <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                {mobileOpen ? (
                  <>
                    <line x1="6" y1="6" x2="18" y2="18" />
                    <line x1="6" y1="18" x2="18" y2="6" />
                  </>
                ) : (
                  <>
                    <line x1="3" y1="6" x2="21" y2="6" />
                    <line x1="3" y1="12" x2="21" y2="12" />
                    <line x1="3" y1="18" x2="21" y2="18" />
                  </>
                )}
              </svg>
            </button>
          </div>
        </div>
        {mobileOpen && (
          <>
            {/* Backdrop: tap anywhere outside the panel to dismiss. */}
            <button
              type="button"
              aria-hidden="true"
              tabIndex={-1}
              onClick={() => setMobileOpen(false)}
              className="xl:hidden fixed inset-0 top-[53px] z-30 bg-background/40 cursor-default"
            />
            <nav className="xl:hidden absolute left-0 right-0 top-full z-40 border-b border-border bg-background px-3 py-2 shadow-lg flex flex-col gap-1 max-h-[calc(100vh-53px)] overflow-y-auto">
              {NAV_ITEMS.map((item) => (
                <Link key={item.path} to={item.path} className={navLinkClass(item.path, true)}>
                  {item.label}
                </Link>
              ))}
            </nav>
          </>
        )}
      </header>
      {location.pathname.startsWith('/ddd') ||
      location.pathname.startsWith('/review') ||
      location.pathname.startsWith('/timeline') ||
      // An individual Agent Workspace (/agents/<slug>) is a full-bleed workbench
      // like DDD; the bare /agents LIST stays in the standard container.
      /^\/agents\/[^/]+/.test(location.pathname) ? (
        // DDD (and the narrative editor at /review) is a full-bleed workspace:
        // persistent left rail + wide main. The page owns its own scroll.
        <main className="h-[calc(100vh-53px)]"><Outlet /></main>
      ) : (
        <main className="mx-auto max-w-7xl px-6 py-8"><Outlet /></main>
      )}
    </div>
  )
}
