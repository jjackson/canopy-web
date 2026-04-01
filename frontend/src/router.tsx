import { createBrowserRouter } from 'react-router-dom'
import { AppLayout } from './components/AppLayout/AppLayout'
import { WorkspacePage } from './pages/WorkspacePage'
import { DiscoveryPage } from './pages/DiscoveryPage'
import { NewCollectionPage } from './pages/NewCollectionPage'
import { SkillDetailPage } from './pages/SkillDetailPage'
import { LeaderboardPage } from './pages/LeaderboardPage'
import { SettingsPage } from './pages/SettingsPage'

export const router = createBrowserRouter([
  {
    element: <AppLayout />,
    children: [
      { path: '/', element: <DiscoveryPage /> },
      { path: '/new', element: <NewCollectionPage /> },
      { path: '/workspace/:sessionId', element: <WorkspacePage /> },
      { path: '/skills/:skillId', element: <SkillDetailPage /> },
      { path: '/leaderboard', element: <LeaderboardPage /> },
      { path: '/settings', element: <SettingsPage /> },
    ],
  },
])
