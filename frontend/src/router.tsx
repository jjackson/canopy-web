import { createBrowserRouter } from 'react-router-dom'
import { AppLayout } from './components/AppLayout/AppLayout'
import { WorkspacePage } from './pages/WorkspacePage'
import { DiscoveryPage } from './pages/DiscoveryPage'
import { SkillDetailPage } from './pages/SkillDetailPage'
import { LeaderboardPage } from './pages/LeaderboardPage'

export const router = createBrowserRouter([
  {
    element: <AppLayout />,
    children: [
      { path: '/', element: <DiscoveryPage /> },
      { path: '/workspace/:sessionId', element: <WorkspacePage /> },
      { path: '/skills/:skillId', element: <SkillDetailPage /> },
      { path: '/leaderboard', element: <LeaderboardPage /> },
    ],
  },
])
