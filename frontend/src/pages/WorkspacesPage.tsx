import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { listWorkspaces } from '@/api/workspace'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
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

import type { WorkspaceSessionListItem as WorkspaceSession } from '@/api/workspace'

const STATUS_FILTERS = [
  { value: '', label: 'All' },
  { value: 'created', label: 'Created' },
  { value: 'analyzing', label: 'Analyzing' },
  { value: 'proposed', label: 'Proposed' },
  { value: 'editing', label: 'Editing' },
  { value: 'testing', label: 'Testing' },
  { value: 'published', label: 'Published' },
]

const STATUS_VARIANTS: Record<string, 'default' | 'secondary'> = {
  published: 'default',
  proposed: 'default',
  editing: 'default',
  analyzing: 'secondary',
  testing: 'secondary',
  created: 'secondary',
}

function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime()
  const minutes = Math.floor(diff / 60000)
  if (minutes < 1) return 'just now'
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  if (days < 7) return `${days}d ago`
  return new Date(iso).toLocaleDateString()
}

export function WorkspacesPage() {
  const navigate = useNavigate()
  const [sessions, setSessions] = useState<WorkspaceSession[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState('')

  useEffect(() => {
    let cancelled = false

    async function load() {
      setLoading(true)
      try {
        const params = statusFilter ? { status: statusFilter } : undefined
        const data = await listWorkspaces(params)
        if (!cancelled) setSessions(data)
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load workspaces')
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    void load()
    return () => { cancelled = true }
  }, [statusFilter])

  const filtered = useMemo(() => {
    if (!search.trim()) return sessions
    const q = search.toLowerCase()
    return sessions.filter(
      (s) =>
        (s.skill_name && s.skill_name.toLowerCase().includes(q)) ||
        (s.collection_name && s.collection_name.toLowerCase().includes(q)),
    )
  }, [sessions, search])

  function handleNew() {
    navigate('/new')
  }

  if (error) {
    return (
      <div className="rounded-lg border border-destructive/30 bg-destructive/10 p-4 text-sm text-destructive">
        {error}
      </div>
    )
  }

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold text-foreground">Workspace Sessions</h1>
          <p className="mt-0.5 text-xs text-muted-foreground">
            Resume in-progress skill extraction sessions or review past ones.
          </p>
        </div>
        <Button size="sm" onClick={handleNew}>
          New Session
        </Button>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <div className="max-w-sm flex-1 min-w-[200px]">
          <Input
            placeholder="Search by skill or collection..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <div className="flex flex-wrap gap-1">
          {STATUS_FILTERS.map((f) => (
            <button
              key={f.value}
              type="button"
              onClick={() => setStatusFilter(f.value)}
              className={`text-xs px-2.5 py-1 rounded border transition-colors ${
                statusFilter === f.value
                  ? 'bg-primary/10 border-primary/30 text-primary'
                  : 'bg-card border-border text-muted-foreground hover:text-foreground-secondary hover:border-input'
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>

      {loading && (
        <div className="space-y-2">
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-8 w-full" />
          <Skeleton className="h-8 w-full" />
        </div>
      )}

      {!loading && (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Skill</TableHead>
              <TableHead>Collection</TableHead>
              <TableHead>Status</TableHead>
              <TableHead className="text-right">Updated</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {filtered.length > 0 ? (
              filtered.map((session) => (
                <TableRow
                  key={session.id}
                  className="cursor-pointer"
                  onClick={() => navigate(`/workspace/${session.id}`)}
                >
                  <TableCell className="font-medium text-foreground">
                    {session.skill_name || <span className="text-muted-foreground italic">Untitled</span>}
                  </TableCell>
                  <TableCell className="text-sm text-foreground-secondary">
                    {session.collection_name || <span className="text-muted-foreground">—</span>}
                  </TableCell>
                  <TableCell>
                    <Badge variant={STATUS_VARIANTS[session.status] || 'secondary'}>
                      {session.status}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-right text-xs text-muted-foreground">
                    {relativeTime(session.updated_at)}
                  </TableCell>
                </TableRow>
              ))
            ) : (
              <TableRow>
                <TableCell colSpan={4} className="h-40 text-center">
                  {sessions.length === 0 ? (
                    <div className="flex flex-col items-center gap-2">
                      <p className="text-sm font-semibold text-foreground-secondary">
                        No workspace sessions {statusFilter ? `with status "${statusFilter}"` : 'yet'}
                      </p>
                      <p className="text-sm text-muted-foreground">
                        Start a new session to extract a skill from a collection.
                      </p>
                      <Button size="sm" className="mt-2" onClick={handleNew}>
                        New Session
                      </Button>
                    </div>
                  ) : (
                    <p className="text-sm text-muted-foreground">No sessions match &ldquo;{search}&rdquo;</p>
                  )}
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      )}
    </div>
  )
}
