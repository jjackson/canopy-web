import { createBrowserRouter } from 'react-router-dom'
import { AppLayout } from './components/AppLayout/AppLayout'

// Placeholder pages
function DiscoveryPage() { return <div className="text-gray-500">Discovery Feed — coming in Task 10</div> }
function WorkspacePage() { return <div className="text-gray-500">Workspace — coming in Task 9</div> }
function SkillDetailPage() { return <div className="text-gray-500">Skill Detail — coming in Task 10</div> }
function LeaderboardPage() { return <div className="text-gray-500">Leaderboard — coming in Task 10</div> }

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
