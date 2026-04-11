import { createBrowserRouter } from 'react-router-dom'
import { AppLayout } from './components/AppLayout/AppLayout'
import { WorkspacePage } from './pages/WorkspacePage'
import { DiscoveryPage } from './pages/DiscoveryPage'
import { ProjectsPage } from './pages/ProjectsPage'
import { NewCollectionPage } from './pages/NewCollectionPage'
import { SkillDetailPage } from './pages/SkillDetailPage'
import { LeaderboardPage } from './pages/LeaderboardPage'
import { SettingsPage } from './pages/SettingsPage'
import { GuidePage } from './pages/GuidePage'
import { ProjectGuidePage } from './pages/ProjectGuidePage'

export const router = createBrowserRouter([
  {
    element: <AppLayout />,
    children: [
      { path: '/', element: <ProjectsPage /> },
      { path: '/skills', element: <DiscoveryPage /> },
      { path: '/projects/:slug/guide', element: <ProjectGuidePage /> },
      { path: '/new', element: <NewCollectionPage /> },
      { path: '/workspace/:sessionId', element: <WorkspacePage /> },
      { path: '/skills/:skillId', element: <SkillDetailPage /> },
      { path: '/leaderboard', element: <LeaderboardPage /> },
      { path: '/guide', element: <GuidePage /> },
      { path: '/settings', element: <SettingsPage /> },
    ],
  },
])
