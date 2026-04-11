import { useEffect, useState, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '@/api/client'
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

interface Skill {
  id: number
  name: string
  description: string
  usage_count: number
  eval_score: number | null
  updated_at: string
}

function formatDate(iso: string): string {
  const d = new Date(iso)
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

export function DiscoveryPage() {
  const navigate = useNavigate()
  const [skills, setSkills] = useState<Skill[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [search, setSearch] = useState('')

  useEffect(() => {
    let cancelled = false

    async function load() {
      try {
        const data = (await api.getSkills('-updated_at')) as Skill[]
        if (!cancelled) setSkills(data)
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load skills')
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    void load()
    return () => { cancelled = true }
  }, [])

  const filtered = useMemo(() => {
    if (!search.trim()) return skills
    const q = search.toLowerCase()
    return skills.filter(
      (s) =>
        s.name.toLowerCase().includes(q) ||
        s.description.toLowerCase().includes(q)
    )
  }, [skills, search])

  function handleNew() {
    navigate('/new')
  }

  if (error) {
    return (
      <div className="rounded-lg border border-red-400/30 bg-red-400/10 p-4 text-sm text-red-400">
        {error}
      </div>
    )
  }

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold text-stone-100">Published Skills</h1>
          <p className="mt-0.5 text-xs text-stone-500">
            Reusable AI skills extracted from conversations and documents.
          </p>
        </div>
        <Button size="sm" onClick={handleNew}>
          New Skill
        </Button>
      </div>

      {/* Search */}
      <div className="max-w-sm">
        <Input
          placeholder="Search skills..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>

      {/* Loading state */}
      {loading && (
        <div className="space-y-2">
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-8 w-full" />
          <Skeleton className="h-8 w-full" />
          <Skeleton className="h-8 w-full" />
        </div>
      )}

      {/* Skills table — always show headers for visual structure */}
      {!loading && (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Description</TableHead>
              <TableHead className="text-right">Runs</TableHead>
              <TableHead className="text-right">Eval Score</TableHead>
              <TableHead className="text-right">Updated</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {filtered.length > 0 ? (
              filtered.map((skill) => (
                <TableRow
                  key={skill.id}
                  className="cursor-pointer"
                  onClick={() => navigate(`/skills/${skill.id}`)}
                >
                  <TableCell className="font-medium text-stone-100">
                    {skill.name}
                  </TableCell>
                  <TableCell className="max-w-xs truncate text-sm text-stone-500">
                    {skill.description}
                  </TableCell>
                  <TableCell className="text-right text-sm text-stone-400 tabular-nums">
                    {skill.usage_count}
                  </TableCell>
                  <TableCell className="text-right">
                    {skill.eval_score != null ? (
                      <Badge variant={skill.eval_score >= 7 ? 'default' : 'secondary'}>
                        {skill.eval_score.toFixed(1)}
                      </Badge>
                    ) : (
                      <span className="text-xs text-stone-600">--</span>
                    )}
                  </TableCell>
                  <TableCell className="text-right text-xs text-stone-500">
                    {formatDate(skill.updated_at)}
                  </TableCell>
                </TableRow>
              ))
            ) : (
              <TableRow>
                <TableCell colSpan={5} className="h-40 text-center">
                  {skills.length === 0 ? (
                    <div className="flex flex-col items-center gap-2">
                      <p className="text-sm font-semibold text-stone-200">No skills yet</p>
                      <p className="text-sm text-stone-500">
                        Paste a conversation to create your first reusable skill.
                      </p>
                      <Button size="sm" className="mt-2" onClick={handleNew}>
                        Create Skill
                      </Button>
                    </div>
                  ) : (
                    <p className="text-sm text-stone-500">No skills match &ldquo;{search}&rdquo;</p>
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
