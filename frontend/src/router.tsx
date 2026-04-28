import { createBrowserRouter } from 'react-router-dom'
import { AppLayout } from './components/AppLayout/AppLayout'
import { WorkspacePage } from './pages/WorkspacePage'
import { WorkspacesPage } from './pages/WorkspacesPage'
import { DiscoveryPage } from './pages/DiscoveryPage'
import { ProjectsPage } from './pages/ProjectsPage'
import { InsightsPage } from './pages/InsightsPage'
import { NewCollectionPage } from './pages/NewCollectionPage'
import { SkillDetailPage } from './pages/SkillDetailPage'
import { LeaderboardPage } from './pages/LeaderboardPage'
import { SettingsPage } from './pages/SettingsPage'
import { GuidePage } from './pages/GuidePage'

export const router = createBrowserRouter([
  {
    element: <AppLayout />,
    children: [
      { path: '/', element: <ProjectsPage /> },
      { path: '/insights', element: <InsightsPage /> },
      { path: '/skills', element: <DiscoveryPage /> },
      { path: '/new', element: <NewCollectionPage /> },
      { path: '/workspaces', element: <WorkspacesPage /> },
      { path: '/workspace/:sessionId', element: <WorkspacePage /> },
      { path: '/skills/:skillId', element: <SkillDetailPage /> },
      { path: '/leaderboard', element: <LeaderboardPage /> },
      { path: '/guide', element: <GuidePage /> },
      { path: '/settings', element: <SettingsPage /> },
    ],
  },
])
