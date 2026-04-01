import { useEffect, useState, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { api } from '@/api/client'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface Step {
  name: string
  description: string
  tools?: string[]
}

interface Skill {
  id: number
  name: string
  description: string
  definition: { steps?: Step[] }
  version: number
  usage_count: number
  eval_score: number | null
  eval_trend: 'improving' | 'declining' | 'stable' | null
  last_eval_at: string | null
  created_at: string
  updated_at: string
}

interface EvalCaseDef {
  id: number
  name: string
  input: string
  expected_output: { contains?: string[] }
}

interface EvalSuite {
  cases: EvalCaseDef[]
  runs_count: number
}

interface CaseResult {
  case_id: number
  case_name: string
  passed: boolean
  reasons: string[]
  output_preview: string
}

interface EvalRun {
  id: number
  status: string
  overall_score: number
  runtime: string
  created_at: string
  results: { cases: CaseResult[] }
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const RUNTIMES = [
  { key: 'web_workflow', label: 'Web Workflow' },
  { key: 'claude_code_skill', label: 'Claude Code Skill' },
  { key: 'open_claw_prompt', label: 'Open Claw Prompt' },
] as const

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatDateTime(iso: string): string {
  const d = new Date(iso)
  return d.toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  })
}

function formatDate(iso: string): string {
  const d = new Date(iso)
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

function scorePercent(score: number): string {
  return (score * 100).toFixed(0) + '%'
}

function TrendIndicator({ trend }: { trend: Skill['eval_trend'] }) {
  if (!trend) return null
  switch (trend) {
    case 'improving':
      return <span className="text-green-600 text-sm font-medium" title="Improving">▲</span>
    case 'declining':
      return <span className="text-red-600 text-sm font-medium" title="Declining">▼</span>
    case 'stable':
      return <span className="text-gray-400 text-sm font-medium" title="Stable">&mdash;</span>
  }
}

function ScoreHistoryBadges({ runs }: { runs: EvalRun[] }) {
  const last5 = runs.slice(0, 5)
  if (last5.length === 0) return null
  return (
    <div className="flex items-center gap-1">
      {last5.map((run) => (
        <span
          key={run.id}
          className={`inline-block rounded px-1.5 py-0.5 text-[10px] font-medium ${
            run.overall_score >= 0.7
              ? 'bg-green-100 text-green-700'
              : run.overall_score >= 0.4
                ? 'bg-yellow-100 text-yellow-700'
                : 'bg-red-100 text-red-700'
          }`}
          title={formatDateTime(run.created_at)}
        >
          {scorePercent(run.overall_score)}
        </span>
      ))}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function EvalCaseEditor({
  skillId,
  cases,
  onUpdate,
}: {
  skillId: number
  cases: EvalCaseDef[]
  onUpdate: () => void
}) {
  const [expandedId, setExpandedId] = useState<number | null>(null)
  const [saving, setSaving] = useState(false)
  const [newTerm, setNewTerm] = useState('')

  function handleExpand(c: EvalCaseDef) {
    if (expandedId === c.id) {
      setExpandedId(null)
      return
    }
    setExpandedId(c.id)
    setNewTerm('')
  }

  async function handleRemoveTerm(c: EvalCaseDef, term: string) {
    setSaving(true)
    try {
      const currentTerms = (c.expected_output?.contains ?? []).filter((t) => t !== term)
      await api.updateEvalCase(skillId, c.id, {
        expected_output: { contains: currentTerms },
      })
      onUpdate()
    } catch {
      // silent
    } finally {
      setSaving(false)
    }
  }

  async function handleAddTerm(c: EvalCaseDef) {
    const term = newTerm.trim()
    if (!term) return
    setSaving(true)
    try {
      const currentTerms = [...(c.expected_output?.contains ?? []), term]
      await api.updateEvalCase(skillId, c.id, {
        expected_output: { contains: currentTerms },
      })
      setNewTerm('')
      onUpdate()
    } catch {
      // silent
    } finally {
      setSaving(false)
    }
  }

  async function handleDelete(caseId: number) {
    setSaving(true)
    try {
      await api.deleteEvalCase(skillId, caseId)
      if (expandedId === caseId) setExpandedId(null)
      onUpdate()
    } catch {
      // silent
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="mt-3 space-y-1">
      {cases.map((c) => {
        const isExpanded = expandedId === c.id
        const terms = c.expected_output?.contains ?? []
        return (
          <div key={c.id} className="rounded border border-gray-200 bg-white">
            <button
              type="button"
              className="flex w-full items-center justify-between px-3 py-2 text-left hover:bg-gray-50"
              onClick={() => handleExpand(c)}
            >
              <span className="text-sm font-medium text-gray-900">{c.name}</span>
              <div className="flex items-center gap-1">
                {terms.map((t) => (
                  <Badge key={t} variant="outline" className="text-[10px]">
                    {t}
                  </Badge>
                ))}
                <span className="ml-1 text-xs text-gray-400">{isExpanded ? '−' : '+'}</span>
              </div>
            </button>
            {isExpanded && (
              <div className="border-t border-gray-100 px-3 py-2 space-y-2">
                <div className="flex flex-wrap gap-1">
                  {terms.map((t) => (
                    <span
                      key={t}
                      className="inline-flex items-center gap-1 rounded bg-gray-100 px-2 py-0.5 text-xs text-gray-700"
                    >
                      {t}
                      <button
                        type="button"
                        className="ml-0.5 text-gray-400 hover:text-red-500"
                        onClick={() => void handleRemoveTerm(c, t)}
                        disabled={saving}
                      >
                        x
                      </button>
                    </span>
                  ))}
                </div>
                <div className="flex gap-2">
                  <Input
                    className="h-7 text-xs"
                    placeholder="Add expected term..."
                    value={newTerm}
                    onChange={(e) => setNewTerm(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') {
                        e.preventDefault()
                        void handleAddTerm(c)
                      }
                    }}
                  />
                  <Button
                    size="sm"
                    variant="outline"
                    className="h-7 text-xs"
                    onClick={() => void handleAddTerm(c)}
                    disabled={saving || !newTerm.trim()}
                  >
                    Add
                  </Button>
                </div>
                <div className="flex justify-end gap-2">
                  <Button
                    size="sm"
                    variant="outline"
                    className="h-7 text-xs text-red-600 hover:text-red-700"
                    onClick={() => void handleDelete(c.id)}
                    disabled={saving}
                  >
                    Delete Case
                  </Button>
                </div>
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}

function RunCaseTable({ cases }: { cases: CaseResult[] }) {
  const [expandedCase, setExpandedCase] = useState<number | null>(null)

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Case</TableHead>
          <TableHead className="text-right">Result</TableHead>
          <TableHead>Reason</TableHead>
          <TableHead className="w-8"></TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {cases.map((r, i) => (
          <>
            <TableRow key={i} className="group">
              <TableCell className="text-sm text-gray-900">{r.case_name}</TableCell>
              <TableCell className="text-right">
                <span
                  className={
                    r.passed
                      ? 'text-xs font-medium text-green-700'
                      : 'text-xs font-medium text-red-700'
                  }
                >
                  {r.passed ? 'PASS' : 'FAIL'}
                </span>
              </TableCell>
              <TableCell className="max-w-xs text-xs">
                {r.passed ? (
                  <span className="text-green-600">
                    {r.reasons.length > 0 ? r.reasons.join('; ') : 'All checks passed'}
                  </span>
                ) : (
                  <span className="text-red-600">
                    {r.reasons.length > 0 ? r.reasons.join('; ') : 'Failed'}
                  </span>
                )}
              </TableCell>
              <TableCell className="w-8">
                {r.output_preview && (
                  <button
                    type="button"
                    className="text-xs text-gray-400 hover:text-gray-600"
                    onClick={() => setExpandedCase(expandedCase === i ? null : i)}
                    title="Toggle output preview"
                  >
                    {expandedCase === i ? '−' : '+'}
                  </button>
                )}
              </TableCell>
            </TableRow>
            {expandedCase === i && r.output_preview && (
              <TableRow key={`${i}-preview`}>
                <TableCell colSpan={4} className="bg-gray-50">
                  <pre className="max-h-32 overflow-auto text-xs text-gray-600 whitespace-pre-wrap">
                    {r.output_preview}
                  </pre>
                </TableCell>
              </TableRow>
            )}
          </>
        ))}
      </TableBody>
    </Table>
  )
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export function SkillDetailPage() {
  const { skillId: skillIdParam } = useParams<{ skillId: string }>()
  const skillId = skillIdParam ? Number(skillIdParam) : null
  const navigate = useNavigate()

  const [skill, setSkill] = useState<Skill | null>(null)
  const [evalSuite, setEvalSuite] = useState<EvalSuite | null>(null)
  const [evalRuns, setEvalRuns] = useState<EvalRun[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [runningEval, setRunningEval] = useState(false)
  const [generatingAdapter, setGeneratingAdapter] = useState<string | null>(null)
  const [adapterOutput, setAdapterOutput] = useState<string | null>(null)

  // Track which eval runs are expanded (latest is expanded by default)
  const [expandedRuns, setExpandedRuns] = useState<Set<number>>(new Set())

  const loadData = useCallback(async () => {
    if (skillId == null || isNaN(skillId)) {
      setError('Invalid skill ID')
      setLoading(false)
      return
    }

    try {
      const [skillData, suiteData, historyData] = await Promise.allSettled([
        api.getSkill(skillId),
        api.getEvalSuite(skillId),
        api.getEvalHistory(skillId),
      ])

      if (skillData.status === 'fulfilled') {
        setSkill(skillData.value as Skill)
      } else {
        setError('Failed to load skill')
        return
      }

      if (suiteData.status === 'fulfilled') {
        setEvalSuite(suiteData.value as EvalSuite)
      }

      if (historyData.status === 'fulfilled') {
        const runs = historyData.value as EvalRun[]
        setEvalRuns(runs)
        // Expand the latest run by default
        if (runs.length > 0) {
          setExpandedRuns(new Set([runs[0].id]))
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load skill')
    } finally {
      setLoading(false)
    }
  }, [skillId])

  useEffect(() => {
    let cancelled = false
    void loadData().then(() => {
      if (cancelled) {
        // reset if unmounted — not strictly necessary but safe
      }
    })
    return () => {
      cancelled = true
    }
  }, [loadData])

  function toggleRunExpanded(runId: number) {
    setExpandedRuns((prev) => {
      const next = new Set(prev)
      if (next.has(runId)) {
        next.delete(runId)
      } else {
        next.add(runId)
      }
      return next
    })
  }

  async function handleRunEval() {
    if (skillId == null) return
    setRunningEval(true)
    try {
      await api.runEval(skillId)
      const [historyData, skillData] = await Promise.all([
        api.getEvalHistory(skillId) as Promise<EvalRun[]>,
        api.getSkill(skillId) as Promise<Skill>,
      ])
      setEvalRuns(historyData)
      setSkill(skillData)
      if (historyData.length > 0) {
        setExpandedRuns(new Set([historyData[0].id]))
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Eval run failed')
    } finally {
      setRunningEval(false)
    }
  }

  async function handleGenerateAdapter(runtime: string) {
    if (skillId == null) return
    setGeneratingAdapter(runtime)
    setAdapterOutput(null)
    try {
      const result = (await api.generateAdapter(skillId, runtime)) as { output?: string }
      setAdapterOutput(result.output ?? JSON.stringify(result, null, 2))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Adapter generation failed')
    } finally {
      setGeneratingAdapter(null)
    }
  }

  async function handleReloadSuite() {
    if (skillId == null) return
    try {
      const suiteData = (await api.getEvalSuite(skillId)) as EvalSuite
      setEvalSuite(suiteData)
    } catch {
      // silent
    }
  }

  // -----------------------------------------------------------------------
  // Render
  // -----------------------------------------------------------------------

  if (loading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-4 w-96" />
        <Skeleton className="h-64 w-full" />
      </div>
    )
  }

  if (error) {
    return (
      <div className="rounded border border-red-200 bg-red-50 p-4 text-sm text-red-700">
        {error}
      </div>
    )
  }

  if (!skill) return null

  const latestRun = evalRuns.length > 0 ? evalRuns[0] : null
  const olderRuns = evalRuns.slice(1)

  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <div className="flex items-center gap-3">
          <h1 className="text-lg font-semibold text-gray-900">{skill.name}</h1>
          <Button
            size="sm"
            variant="outline"
            onClick={() => navigate(`/new?revise=${skill.id}`)}
          >
            Revise
          </Button>
          <Badge variant="outline">v{skill.version}</Badge>
          <Badge variant="secondary">{skill.usage_count} runs</Badge>
          {skill.eval_score != null && (
            <div className="flex items-center gap-1">
              <Badge variant={skill.eval_score >= 0.7 ? 'default' : 'secondary'}>
                {scorePercent(skill.eval_score)}
              </Badge>
              <TrendIndicator trend={skill.eval_trend} />
            </div>
          )}
          <ScoreHistoryBadges runs={evalRuns} />
        </div>
        <p className="mt-1 text-sm text-gray-500">{skill.description}</p>
      </div>

      {/* Steps */}
      {skill.definition?.steps && skill.definition.steps.length > 0 && (
        <section>
          <h2 className="text-sm font-semibold text-gray-900">Steps</h2>
          <ol className="mt-2 space-y-2">
            {skill.definition.steps.map((step, i) => (
              <li key={i} className="flex gap-3">
                <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-gray-100 text-xs font-medium text-gray-500">
                  {i + 1}
                </span>
                <div className="min-w-0">
                  <p className="text-sm font-medium text-gray-900">{step.name}</p>
                  <p className="text-sm text-gray-500">{step.description}</p>
                  {step.tools && step.tools.length > 0 && (
                    <div className="mt-1 flex flex-wrap gap-1">
                      {step.tools.map((tool) => (
                        <Badge key={tool} variant="outline">
                          {tool}
                        </Badge>
                      ))}
                    </div>
                  )}
                </div>
              </li>
            ))}
          </ol>
        </section>
      )}

      {/* Eval Section */}
      <section>
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-gray-900">Eval Suite</h2>
          <Button
            size="sm"
            variant="outline"
            onClick={() => void handleRunEval()}
            disabled={runningEval}
          >
            {runningEval ? 'Running...' : 'Run Eval'}
          </Button>
        </div>

        {evalSuite ? (
          <>
            <div className="mt-2 flex gap-4 text-xs text-gray-400">
              <span>{evalSuite.cases.length} cases</span>
              <span>&middot;</span>
              <span>{evalSuite.runs_count} runs</span>
            </div>

            {/* Eval case editor */}
            {skillId != null && (
              <EvalCaseEditor
                skillId={skillId}
                cases={evalSuite.cases}
                onUpdate={() => void handleReloadSuite()}
              />
            )}
          </>
        ) : (
          <p className="mt-2 text-sm text-gray-500">No eval suite configured.</p>
        )}

        {/* Latest run — expanded */}
        {latestRun && (
          <div className="mt-4 space-y-3">
            <h3 className="text-xs font-medium text-gray-500">Recent Runs</h3>

            <div className="rounded border border-gray-200 bg-white">
              <button
                type="button"
                className="flex w-full items-center justify-between px-3 py-2 hover:bg-gray-50"
                onClick={() => toggleRunExpanded(latestRun.id)}
              >
                <div className="flex items-center gap-2">
                  <Badge variant={latestRun.overall_score >= 0.7 ? 'default' : 'secondary'}>
                    {scorePercent(latestRun.overall_score)}
                  </Badge>
                  <span className="text-xs text-gray-400">
                    {formatDateTime(latestRun.created_at)}
                  </span>
                  {latestRun.runtime != null && (
                    <span className="text-xs text-gray-300">
                      {latestRun.runtime}
                    </span>
                  )}
                  <Badge variant="outline" className="text-[10px]">latest</Badge>
                </div>
                <span className="text-xs text-gray-400">
                  {expandedRuns.has(latestRun.id) ? '−' : '+'}
                </span>
              </button>
              {expandedRuns.has(latestRun.id) &&
                latestRun.results?.cases &&
                latestRun.results.cases.length > 0 && (
                  <div className="border-t border-gray-100 p-3">
                    <RunCaseTable cases={latestRun.results.cases} />
                  </div>
                )}
            </div>

            {/* Older runs — collapsed by default */}
            {olderRuns.map((run) => (
              <div key={run.id} className="rounded border border-gray-200 bg-white">
                <button
                  type="button"
                  className="flex w-full items-center justify-between px-3 py-2 hover:bg-gray-50"
                  onClick={() => toggleRunExpanded(run.id)}
                >
                  <div className="flex items-center gap-2">
                    <Badge variant={run.overall_score >= 0.7 ? 'default' : 'secondary'}>
                      {scorePercent(run.overall_score)}
                    </Badge>
                    <span className="text-xs text-gray-400">
                      {formatDate(run.created_at)}
                    </span>
                    {run.runtime != null && (
                      <span className="text-xs text-gray-300">
                        {run.runtime}
                      </span>
                    )}
                  </div>
                  <span className="text-xs text-gray-400">
                    {expandedRuns.has(run.id) ? '−' : '+'}
                  </span>
                </button>
                {expandedRuns.has(run.id) &&
                  run.results?.cases &&
                  run.results.cases.length > 0 && (
                    <div className="border-t border-gray-100 p-3">
                      <RunCaseTable cases={run.results.cases} />
                    </div>
                  )}
              </div>
            ))}
          </div>
        )}

        {evalRuns.length === 0 && (
          <p className="mt-4 text-sm text-gray-500">
            No eval runs yet. Click "Run Eval" to get started.
          </p>
        )}
      </section>

      {/* Runtime Adapters */}
      <section>
        <h2 className="text-sm font-semibold text-gray-900">Runtime Adapters</h2>
        <div className="mt-2 flex gap-2">
          {RUNTIMES.map((rt) => (
            <Button
              key={rt.key}
              size="sm"
              variant="outline"
              onClick={() => void handleGenerateAdapter(rt.key)}
              disabled={generatingAdapter != null}
            >
              {generatingAdapter === rt.key ? 'Generating...' : rt.label}
            </Button>
          ))}
        </div>
        {adapterOutput && (
          <pre className="mt-3 max-h-64 overflow-auto rounded border border-gray-200 bg-gray-50 p-3 text-xs text-gray-700">
            {adapterOutput}
          </pre>
        )}
      </section>
    </div>
  )
}
