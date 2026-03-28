import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '@/api/client'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'

interface Skill {
  id: number
  name: string
  usage_count: number
  eval_score: number | null
  updated_at: string
}

function formatDate(iso: string): string {
  const d = new Date(iso)
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

export function LeaderboardPage() {
  const navigate = useNavigate()
  const [skills, setSkills] = useState<Skill[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false

    async function load() {
      try {
        const data = (await api.getSkills('-usage_count')) as Skill[]
        if (!cancelled) setSkills(data)
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load leaderboard')
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    void load()
    return () => { cancelled = true }
  }, [])

  if (error) {
    return (
      <div className="rounded border border-red-200 bg-red-50 p-4 text-sm text-red-700">
        {error}
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <h1 className="text-lg font-semibold text-gray-900">Leaderboard</h1>

      {/* Loading */}
      {loading && (
        <div className="space-y-2">
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-8 w-full" />
          <Skeleton className="h-8 w-full" />
          <Skeleton className="h-8 w-full" />
        </div>
      )}

      {/* Table — always show headers for visual structure */}
      {!loading && (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Skill</TableHead>
              <TableHead className="text-right">Eval Score</TableHead>
              <TableHead className="text-right">Trend</TableHead>
              <TableHead className="text-right">Runs</TableHead>
              <TableHead className="text-right">Last Updated</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {skills.length > 0 ? (
              skills.map((skill) => (
                <TableRow
                  key={skill.id}
                  className="cursor-pointer"
                  onClick={() => navigate(`/skills/${skill.id}`)}
                >
                  <TableCell className="font-medium text-gray-900">
                    {skill.name}
                  </TableCell>
                  <TableCell className="text-right">
                    {skill.usage_count < 2 ? (
                      <span className="text-xs text-gray-400">needs data</span>
                    ) : skill.eval_score != null ? (
                      <Badge variant={skill.eval_score >= 7 ? 'default' : 'secondary'}>
                        {skill.eval_score.toFixed(1)}
                      </Badge>
                    ) : (
                      <span className="text-xs text-gray-400">--</span>
                    )}
                  </TableCell>
                  <TableCell className="text-right text-xs text-gray-400">
                    --
                  </TableCell>
                  <TableCell className="text-right text-sm text-gray-500">
                    {skill.usage_count}
                  </TableCell>
                  <TableCell className="text-right text-xs text-gray-400">
                    {formatDate(skill.updated_at)}
                  </TableCell>
                </TableRow>
              ))
            ) : (
              <TableRow>
                <TableCell colSpan={5} className="h-32 text-center">
                  <p className="text-sm font-medium text-gray-900">No eval data yet</p>
                  <p className="mt-1 text-sm text-gray-500">
                    Run some evals to see the leaderboard.
                  </p>
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      )}
    </div>
  )
}
