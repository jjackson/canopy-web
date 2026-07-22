import { Outlet } from 'react-router-dom'
import { ThemeProvider } from '@/theme/ThemeProvider'

/**
 * Chrome-less layout for public, anonymous-capable pages (the DDD release
 * surface). Just theme context + an <Outlet/> — deliberately NO TopNav / no
 * workspace-aware nav, because those fire authed calls that would bounce an
 * anonymous visitor to login. Mounted OUTSIDE the app shell in the router.
 */
export function PublicLayout() {
  return (
    <ThemeProvider>
      <Outlet />
    </ThemeProvider>
  )
}
