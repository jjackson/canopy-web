import { createBrowserRouter, Navigate } from 'react-router-dom'
import { AppLayout } from './components/AppLayout/AppLayout'
import { WorkspacePage } from './pages/WorkspacePage'
import { WorkspacesPage } from './pages/WorkspacesPage'
import { DiscoveryPage } from './pages/DiscoveryPage'
import { ProjectsPage } from './pages/ProjectsPage'
import { InsightsPage } from './pages/InsightsPage'
import { NewCollectionPage } from './pages/NewCollectionPage'
import { SkillDetailPage } from './pages/SkillDetailPage'
import { SettingsPage } from './pages/SettingsPage'
import { GuidePage } from './pages/GuidePage'
import { WalkthroughsPage } from './pages/WalkthroughsPage'
import { WalkthroughViewerPage } from './pages/WalkthroughViewerPage'
import { ReviewPage } from './pages/ReviewPage'
import { DddPage } from './pages/DddPage'
import { DddPlansPage } from './pages/DddPlansPage'

export const router = createBrowserRouter([
  {
    element: <AppLayout />,
    children: [
      { path: '/', element: <ProjectsPage /> },
      { path: '/insights', element: <InsightsPage /> },
      { path: '/skills', element: <DiscoveryPage /> },
      { path: '/walkthroughs', element: <WalkthroughsPage /> },
      { path: '/w/:id', element: <WalkthroughViewerPage /> },
      { path: '/ddd', element: <DddPage /> },
      { path: '/ddd/:narrative', element: <DddPage /> },
      { path: '/ddd/:narrative/:runId', element: <DddPage /> },
      { path: '/ddd-plans', element: <DddPlansPage /> },
      { path: '/reviews', element: <Navigate to="/ddd-plans" replace /> },
      { path: '/review/:id', element: <ReviewPage /> },
      { path: '/new', element: <NewCollectionPage /> },
      { path: '/workspaces', element: <WorkspacesPage /> },
      { path: '/workspace/:sessionId', element: <WorkspacePage /> },
      { path: '/skills/:skillId', element: <SkillDetailPage /> },
      { path: '/guide', element: <GuidePage /> },
      { path: '/settings', element: <SettingsPage /> },
    ],
  },
])
