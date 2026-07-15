import { lazy, Suspense } from 'react'
import { createBrowserRouter, Navigate, useLocation, useParams } from 'react-router-dom'
import { useWorkspace } from './workspace/WorkspaceProvider'
import { AppLayout } from './components/AppLayout/AppLayout'
import { ProjectsPage } from './pages/ProjectsPage'
import { InsightsPage } from './pages/InsightsPage'
import { ShareoutsPage } from './pages/ShareoutsPage'
import { SettingsPage } from './pages/SettingsPage'
import { WalkthroughsPage } from './pages/WalkthroughsPage'
import { WalkthroughViewerPage } from './pages/WalkthroughViewerPage'
import { ReviewPage } from './pages/ReviewPage'
import { DddPage } from './pages/DddPage'
import { TimelinePage } from './pages/TimelinePage'
import { SystemPage } from './pages/SystemPage'
import { SessionsPage } from './pages/SessionsPage'
import { AgentsPage } from './pages/AgentsPage'
import { AgentWorkspacePage } from './pages/AgentWorkspacePage'
import SessionSharePage from './pages/SessionSharePage'

// Agent Workspace sections are lazy-loaded — each owns its data fetch and only
// the active section's bundle is pulled in.
const NeedsYouSection = lazy(() =>
  import('./pages/agents/NeedsYouSection').then((m) => ({ default: m.NeedsYouSection })),
)
const AgentOverviewSection = lazy(() =>
  import('./pages/agents/AgentOverviewSection').then((m) => ({ default: m.AgentOverviewSection })),
)
const AgentTasksSection = lazy(() =>
  import('./pages/agents/AgentTasksSection').then((m) => ({ default: m.AgentTasksSection })),
)
const AgentTurnsSection = lazy(() =>
  import('./pages/agents/AgentTurnsSection').then((m) => ({ default: m.AgentTurnsSection })),
)
const SchedulesSection = lazy(() =>
  import('./pages/agents/SchedulesSection').then((m) => ({ default: m.SchedulesSection })),
)
const AgentSyncsSection = lazy(() =>
  import('./pages/agents/AgentSyncsSection').then((m) => ({ default: m.AgentSyncsSection })),
)
const AgentWorkProductsSection = lazy(() =>
  import('./pages/agents/AgentWorkProductsSection').then((m) => ({ default: m.AgentWorkProductsSection })),
)
const AgentSkillsSection = lazy(() =>
  import('./pages/agents/AgentSkillsSection').then((m) => ({ default: m.AgentSkillsSection })),
)

// Each lazy section renders inside the workspace shell's scrolling <main>; this
// keeps a minimal fallback in that same content area while the chunk loads.
function LazySection({ children }: { children: React.ReactNode }) {
  return (
    <Suspense
      fallback={
        <div className="max-w-4xl px-6 py-8 text-[13px] text-muted-foreground">Loading…</div>
      }
    >
      {children}
    </Suspense>
  )
}

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

// Legacy flat tenant surface (e.g. /agents, /ddd/foo) → the active workspace's
// scoped path. Waits for the workspace list so `active` is known.
function TenantRedirect({ to }: { to: string }) {
  const { active, loading } = useWorkspace()
  const { '*': tail } = useParams()
  if (loading) return null
  if (!active) return null // no membership yet; nothing to route to
  const suffix = tail ? `/${tail}` : ''
  return <Navigate to={`/w/${active}/${to}${suffix}`} replace />
}

// Bare "/" → the active workspace's workbench.
function RootRedirect() {
  const { active, loading } = useWorkspace()
  if (loading) return null
  if (!active) return null
  return <Navigate to={`/w/${active}`} replace />
}

// /w/:workspace index. Disambiguates a legacy /w/<uuid> walkthrough link
// (redirect to the new viewer) from a real workspace slug (render the workbench).
function WorkspaceIndex() {
  const { workspace } = useParams()
  const { search, hash } = useLocation()
  if (workspace && UUID_RE.test(workspace)) {
    // Preserve ?t=<share_token> and #t=<seconds> across the redirect.
    return <Navigate to={`/walkthrough/${workspace}${search}${hash}`} replace />
  }
  return <ProjectsPage />
}

export const router = createBrowserRouter([
  {
    element: <AppLayout />,
    children: [
      // --- Personal / global (not tenant-scoped) ---
      { path: '/system', element: <SystemPage /> },
      { path: '/insights', element: <InsightsPage /> },
      { path: '/sessions', element: <SessionsPage /> },
      { path: '/settings', element: <SettingsPage /> },
      // --- Public viewers (root; self-enforce visibility) ---
      { path: '/walkthrough/:id', element: <WalkthroughViewerPage /> },
      { path: '/review/:id', element: <ReviewPage /> },

      // --- Tenant-scoped surfaces under /w/:workspace ---
      { path: '/w/:workspace', element: <WorkspaceIndex /> },
      { path: '/w/:workspace/timeline', element: <TimelinePage /> },
      { path: '/w/:workspace/shareouts', element: <ShareoutsPage /> },
      { path: '/w/:workspace/shareouts/:period', element: <ShareoutsPage /> },
      { path: '/w/:workspace/walkthroughs', element: <WalkthroughsPage /> },
      { path: '/w/:workspace/agents', element: <AgentsPage /> },
      {
        path: '/w/:workspace/agents/:slug',
        element: <AgentWorkspacePage />,
        children: [
          { index: true, element: <Navigate to="needs-you" replace /> },
          { path: 'needs-you', element: <LazySection><NeedsYouSection /></LazySection> },
          { path: 'overview', element: <LazySection><AgentOverviewSection /></LazySection> },
          { path: 'tasks', element: <LazySection><AgentTasksSection /></LazySection> },
          { path: 'turns', element: <LazySection><AgentTurnsSection /></LazySection> },
          { path: 'schedules', element: <LazySection><SchedulesSection /></LazySection> },
          { path: 'syncs', element: <LazySection><AgentSyncsSection /></LazySection> },
          { path: 'work-products', element: <LazySection><AgentWorkProductsSection /></LazySection> },
          { path: 'skills', element: <LazySection><AgentSkillsSection /></LazySection> },
        ],
      },
      { path: '/w/:workspace/ddd', element: <DddPage /> },
      { path: '/w/:workspace/ddd/:narrative', element: <DddPage /> },
      { path: '/w/:workspace/ddd/:narrative/:runId', element: <DddPage /> },

      // --- Legacy flat paths → active workspace (or new viewer) ---
      { path: '/', element: <RootRedirect /> },
      { path: '/timeline', element: <TenantRedirect to="timeline" /> },
      { path: '/shareouts/*', element: <TenantRedirect to="shareouts" /> },
      { path: '/walkthroughs', element: <TenantRedirect to="walkthroughs" /> },
      { path: '/agents/*', element: <TenantRedirect to="agents" /> },
      { path: '/ddd/*', element: <TenantRedirect to="ddd" /> },
      { path: '/ddd-plans', element: <Navigate to="/" replace /> },
      { path: '/reviews', element: <Navigate to="/" replace /> },
    ],
  },
  // Public, chrome-less route — mounted OUTSIDE AppLayout so anonymous
  // visitors aren't bounced to login by the app shell's authed calls.
  { path: '/share/:token', element: <SessionSharePage /> },
], {
  // "/" at root, "/canopy" as a labs tenant — keeps every route + <Link> under
  // the deployment's path prefix (from Vite's import.meta.env.BASE_URL).
  basename: import.meta.env.BASE_URL.replace(/\/$/, '') || '/',
})
