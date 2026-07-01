import { lazy, Suspense } from 'react'
import { createBrowserRouter, Navigate, useParams } from 'react-router-dom'
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

// Legacy /w/<uuid> walkthrough links → the new /walkthrough/<uuid> viewer.
function LegacyWalkthroughRedirect() {
  const { id } = useParams()
  return <Navigate to={`/walkthrough/${id}`} replace />
}

// Bare /agents (+ deep links) → the active workspace's scoped agents surface.
// Waits for the workspace list to resolve so `active` is known.
function AgentsRedirect() {
  const { active, loading } = useWorkspace()
  const { '*': tail } = useParams()
  if (loading) return null
  if (!active) return <Navigate to="/" replace />
  const suffix = tail ? `/${tail}` : ''
  return <Navigate to={`/w/${active}/agents${suffix}`} replace />
}

export const router = createBrowserRouter([
  {
    element: <AppLayout />,
    children: [
      { path: '/', element: <ProjectsPage /> },
      { path: '/timeline', element: <TimelinePage /> },
      { path: '/system', element: <SystemPage /> },
      { path: '/insights', element: <InsightsPage /> },
      { path: '/shareouts', element: <ShareoutsPage /> },
      { path: '/shareouts/:period', element: <ShareoutsPage /> },
      { path: '/walkthroughs', element: <WalkthroughsPage /> },
      // Public walkthrough viewer (reclaimed /w/ for workspaces).
      { path: '/walkthrough/:id', element: <WalkthroughViewerPage /> },
      { path: '/w/:id', element: <LegacyWalkthroughRedirect /> },
      { path: '/sessions', element: <SessionsPage /> },
      // Agents are workspace-scoped: mounted under /w/:workspace. Legacy
      // /agents(/…) redirects to the active workspace.
      { path: '/agents/*', element: <AgentsRedirect /> },
      { path: '/w/:workspace/agents', element: <AgentsPage /> },
      {
        path: '/w/:workspace/agents/:slug',
        element: <AgentWorkspacePage />,
        children: [
          { index: true, element: <Navigate to="needs-you" replace /> },
          { path: 'needs-you', element: <LazySection><NeedsYouSection /></LazySection> },
          { path: 'overview', element: <LazySection><AgentOverviewSection /></LazySection> },
          { path: 'tasks', element: <LazySection><AgentTasksSection /></LazySection> },
          { path: 'syncs', element: <LazySection><AgentSyncsSection /></LazySection> },
          { path: 'work-products', element: <LazySection><AgentWorkProductsSection /></LazySection> },
          { path: 'skills', element: <LazySection><AgentSkillsSection /></LazySection> },
        ],
      },
      { path: '/ddd', element: <DddPage /> },
      { path: '/ddd/:narrative', element: <DddPage /> },
      { path: '/ddd/:narrative/:runId', element: <DddPage /> },
      { path: '/ddd-plans', element: <Navigate to="/ddd" replace /> },
      { path: '/reviews', element: <Navigate to="/ddd" replace /> },
      { path: '/review/:id', element: <ReviewPage /> },
      { path: '/settings', element: <SettingsPage /> },
    ],
  },
  // Public, chrome-less route — mounted OUTSIDE AppLayout so anonymous
  // visitors aren't bounced to login by the app shell's authed calls.
  { path: '/share/:token', element: <SessionSharePage /> },
])
