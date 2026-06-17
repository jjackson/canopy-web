import { createBrowserRouter, Navigate } from 'react-router-dom'
import { AppLayout } from './components/AppLayout/AppLayout'
import { WorkspacePage } from './pages/WorkspacePage'
import { WorkspacesPage } from './pages/WorkspacesPage'
import { DiscoveryPage } from './pages/DiscoveryPage'
import { ProjectsPage } from './pages/ProjectsPage'
import { InsightsPage } from './pages/InsightsPage'
import { ShareoutsPage } from './pages/ShareoutsPage'
import { NewCollectionPage } from './pages/NewCollectionPage'
import { SkillDetailPage } from './pages/SkillDetailPage'
import { SettingsPage } from './pages/SettingsPage'
import { GuidePage } from './pages/GuidePage'
import { WalkthroughsPage } from './pages/WalkthroughsPage'
import { WalkthroughViewerPage } from './pages/WalkthroughViewerPage'
import { ReviewPage } from './pages/ReviewPage'
import { DddPage } from './pages/DddPage'
import { SessionsPage } from './pages/SessionsPage'
import { AgentsPage } from './pages/AgentsPage'
import { AgentWorkspacePage } from './pages/AgentWorkspacePage'
import SessionSharePage from './pages/SessionSharePage'

export const router = createBrowserRouter([
  {
    element: <AppLayout />,
    children: [
      { path: '/', element: <ProjectsPage /> },
      { path: '/insights', element: <InsightsPage /> },
      { path: '/shareouts', element: <ShareoutsPage /> },
      { path: '/shareouts/:period', element: <ShareoutsPage /> },
      { path: '/skills', element: <DiscoveryPage /> },
      { path: '/walkthroughs', element: <WalkthroughsPage /> },
      { path: '/w/:id', element: <WalkthroughViewerPage /> },
      { path: '/sessions', element: <SessionsPage /> },
      { path: '/agents', element: <AgentsPage /> },
      { path: '/agents/:slug', element: <AgentWorkspacePage /> },
      { path: '/ddd', element: <DddPage /> },
      { path: '/ddd/:narrative', element: <DddPage /> },
      { path: '/ddd/:narrative/:runId', element: <DddPage /> },
      { path: '/ddd-plans', element: <Navigate to="/ddd" replace /> },
      { path: '/reviews', element: <Navigate to="/ddd" replace /> },
      { path: '/review/:id', element: <ReviewPage /> },
      { path: '/new', element: <NewCollectionPage /> },
      { path: '/workspaces', element: <WorkspacesPage /> },
      { path: '/workspace/:sessionId', element: <WorkspacePage /> },
      { path: '/skills/:skillId', element: <SkillDetailPage /> },
      { path: '/guide', element: <GuidePage /> },
      { path: '/settings', element: <SettingsPage /> },
    ],
  },
  // Public, chrome-less route — mounted OUTSIDE AppLayout so anonymous
  // visitors aren't bounced to login by the app shell's authed calls.
  { path: '/share/:token', element: <SessionSharePage /> },
])
