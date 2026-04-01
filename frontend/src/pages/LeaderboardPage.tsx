import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '@/api/client'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
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
  description: string
  version: number
  usage_count: number
  eval_score: number | null
  eval_trend: 'improving' | 'declining' | 'stable' | null
  last_eval_at: string | null
  created_at: string
  updated_at: string
}

type SortField = 'eval_score' | 'usage_count' | 'name' | 'last_eval_at'
type SortDir = 'asc' | 'desc'

const STALE_THRESHOLD_MS = 7 * 24 * 60 * 60 * 1000 // 7 days

function isStale(lastEvalAt: string | null): boolean {
  if (!lastEvalAt) return true
  return Date.now() - new Date(lastEvalAt).getTime() > STALE_THRESHOLD_MS
}

function relativeTime(iso: string | null): string {
  if (!iso) return 'Never'
  const diff = Date.now() - new Date(iso).getTime()
  const seconds = Math.floor(diff / 1000)
  const minutes = Math.floor(seconds / 60)
  const hours = Math.floor(minutes / 60)
  const days = Math.floor(hours / 24)
  const weeks = Math.floor(days / 7)
  const months = Math.floor(days / 30)

  if (months > 0) return `${months} month${months > 1 ? 's' : ''} ago`
  if (weeks > 0) return `${weeks} week${weeks > 1 ? 's' : ''} ago`
  if (days > 0) return `${days} day${days > 1 ? 's' : ''} ago`
  if (hours > 0) return `${hours} hour${hours > 1 ? 's' : ''} ago`
  if (minutes > 0) return `${minutes} min${minutes > 1 ? 's' : ''} ago`
  return 'Just now'
}

function TrendIndicator({ trend }: { trend: Skill['eval_trend'] }) {
  switch (trend) {
    case 'improving':
      return <span className="text-green-600 font-medium">▲</span>
    case 'declining':
      return <span className="text-red-600 font-medium">▼</span>
    case 'stable':
    default:
      return <span className="text-gray-400">—</span>
  }
}

function ScoreBadge({ score }: { score: number | null }) {
  if (score == null) {
    return <span className="text-xs text-gray-400">--</span>
  }

  const pct = Math.round(score * 100)
  let colorClass: string

  if (score >= 0.8) {
    colorClass = 'text-green-700 bg-green-50 border-green-200'
  } else if (score >= 0.5) {
    colorClass = 'text-amber-700 bg-amber-50 border-amber-200'
  } else {
    colorClass = 'text-red-700 bg-red-50 border-red-200'
  }

  return (
    <Badge variant="outline" className={colorClass}>
      {pct}%
    </Badge>
  )
}

function SortableHeader({
  label,
  field,
  sortField,
  sortDir,
  onSort,
  className,
}: {
  label: string
  field: SortField
  sortField: SortField
  sortDir: SortDir
  onSort: (field: SortField) => void
  className?: string
}) {
  const active = sortField === field
  return (
    <TableHead className={className}>
      <Button
        variant="ghost"
        size="xs"
        className={`-ml-2 font-medium ${active ? 'text-foreground' : 'text-muted-foreground'}`}
        onClick={() => onSort(field)}
      >
        {label}
        {active ? (
          <span className="ml-1 text-[10px]">{sortDir === 'desc' ? '↓' : '↑'}</span>
        ) : null}
      </Button>
    </TableHead>
  )
}

export function LeaderboardPage() {
  const navigate = useNavigate()
  const [skills, setSkills] = useState<Skill[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [sortField, setSortField] = useState<SortField>('eval_score')
  const [sortDir, setSortDir] = useState<SortDir>('desc')

  useEffect(() => {
    let cancelled = false

    async function load() {
      try {
        const data = (await api.getSkills()) as Skill[]
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

  function handleSort(field: SortField) {
    if (field === sortField) {
      setSortDir((prev) => (prev === 'desc' ? 'asc' : 'desc'))
    } else {
      setSortField(field)
      setSortDir('desc')
    }
  }

  const sorted = useMemo(() => {
    const copy = [...skills]
    const dir = sortDir === 'desc' ? -1 : 1

    copy.sort((a, b) => {
      let aVal: number | string
      let bVal: number | string

      switch (sortField) {
        case 'eval_score':
          // Nulls always sort to the bottom regardless of direction
          if (a.eval_score == null && b.eval_score == null) return 0
          if (a.eval_score == null) return 1
          if (b.eval_score == null) return -1
          aVal = a.eval_score
          bVal = b.eval_score
          break
        case 'usage_count':
          aVal = a.usage_count
          bVal = b.usage_count
          break
        case 'name':
          aVal = a.name.toLowerCase()
          bVal = b.name.toLowerCase()
          break
        case 'last_eval_at':
          // Nulls sort to bottom
          if (!a.last_eval_at && !b.last_eval_at) return 0
          if (!a.last_eval_at) return 1
          if (!b.last_eval_at) return -1
          aVal = new Date(a.last_eval_at).getTime()
          bVal = new Date(b.last_eval_at).getTime()
          break
        default:
          return 0
      }

      if (aVal < bVal) return -1 * dir
      if (aVal > bVal) return 1 * dir
      return 0
    })

    return copy
  }, [skills, sortField, sortDir])

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

      {loading && (
        <div className="space-y-2">
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-8 w-full" />
          <Skeleton className="h-8 w-full" />
          <Skeleton className="h-8 w-full" />
        </div>
      )}

      {!loading && (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-8 text-right text-muted-foreground">#</TableHead>
              <SortableHeader
                label="Skill"
                field="name"
                sortField={sortField}
                sortDir={sortDir}
                onSort={handleSort}
              />
              <SortableHeader
                label="Eval Score"
                field="eval_score"
                sortField={sortField}
                sortDir={sortDir}
                onSort={handleSort}
                className="text-right"
              />
              <TableHead className="text-right">Trend</TableHead>
              <SortableHeader
                label="Runs"
                field="usage_count"
                sortField={sortField}
                sortDir={sortDir}
                onSort={handleSort}
                className="text-right"
              />
              <SortableHeader
                label="Last Eval"
                field="last_eval_at"
                sortField={sortField}
                sortDir={sortDir}
                onSort={handleSort}
                className="text-right"
              />
            </TableRow>
          </TableHeader>
          <TableBody>
            {sorted.length > 0 ? (
              sorted.map((skill, idx) => {
                const stale = isStale(skill.last_eval_at)
                return (
                  <TableRow
                    key={skill.id}
                    className={`cursor-pointer ${stale ? 'bg-amber-50/60' : ''}`}
                    onClick={() => navigate(`/skills/${skill.id}`)}
                  >
                    <TableCell className="text-right text-xs text-gray-400 tabular-nums">
                      {idx + 1}
                    </TableCell>
                    <TableCell className="font-medium text-gray-900">
                      {skill.name}
                    </TableCell>
                    <TableCell className="text-right">
                      <ScoreBadge score={skill.eval_score} />
                    </TableCell>
                    <TableCell className="text-right">
                      <TrendIndicator trend={skill.eval_trend} />
                    </TableCell>
                    <TableCell className="text-right text-sm text-gray-500 tabular-nums">
                      {skill.usage_count}
                    </TableCell>
                    <TableCell className="text-right text-xs text-gray-400">
                      <span className="inline-flex items-center gap-1.5">
                        {relativeTime(skill.last_eval_at)}
                        {stale && (
                          <Badge variant="outline" className="text-amber-600 border-amber-300 bg-amber-50 text-[10px] px-1 py-0">
                            stale
                          </Badge>
                        )}
                      </span>
                    </TableCell>
                  </TableRow>
                )
              })
            ) : (
              <TableRow>
                <TableCell colSpan={6} className="h-32 text-center">
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
