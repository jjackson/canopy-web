import { Outlet, Link, useLocation } from 'react-router-dom'
import { clsx } from 'clsx'

const NAV_ITEMS = [
  { path: '/', label: 'Skills' },
  { path: '/leaderboard', label: 'Leaderboard' },
]

export function AppLayout() {
  const location = useLocation()
  return (
    <div className="min-h-screen bg-gray-50">
      <header className="border-b border-gray-200 bg-white">
        <div className="mx-auto max-w-7xl px-6 py-3 flex items-center justify-between">
          <Link to="/" className="text-lg font-semibold text-gray-900">Canopy</Link>
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
        </div>
      </header>
      <main className="mx-auto max-w-7xl px-6 py-8"><Outlet /></main>
    </div>
  )
}
