import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { api } from '@/api/client'
import { Button } from '@/components/ui/button'
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

interface Step {
  name: string
  description: string
  tools?: string[]
}

interface Skill {
  id: number
  name: string
  description: string
  version: number
  usage_count: number
  eval_score: number | null
  steps: Step[]
  updated_at: string
}

interface EvalCase {
  name: string
  input: string
  expected_output: string
}

interface EvalSuite {
  cases: EvalCase[]
  runs_count: number
}

interface CaseResult {
  case_name: string
  passed: boolean
  reason?: string
}

interface EvalRun {
  id: number
  score: number
  created_at: string
  results: CaseResult[]
}

const RUNTIMES = [
  { key: 'web_workflow', label: 'Web Workflow' },
  { key: 'claude_code_skill', label: 'Claude Code Skill' },
  { key: 'open_claw_prompt', label: 'Open Claw Prompt' },
] as const

function formatDateTime(iso: string): string {
  const d = new Date(iso)
  return d.toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  })
}

export function SkillDetailPage() {
  const { skillId: skillIdParam } = useParams<{ skillId: string }>()
  const skillId = skillIdParam ? Number(skillIdParam) : null

  const [skill, setSkill] = useState<Skill | null>(null)
  const [evalSuite, setEvalSuite] = useState<EvalSuite | null>(null)
  const [evalRuns, setEvalRuns] = useState<EvalRun[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [runningEval, setRunningEval] = useState(false)
  const [generatingAdapter, setGeneratingAdapter] = useState<string | null>(null)
  const [adapterOutput, setAdapterOutput] = useState<string | null>(null)

  useEffect(() => {
    if (skillId == null || isNaN(skillId)) {
      setError('Invalid skill ID')
      setLoading(false)
      return
    }

    let cancelled = false

    async function load() {
      try {
        const [skillData, suiteData, historyData] = await Promise.allSettled([
          api.getSkill(skillId!),
          api.getEvalSuite(skillId!),
          api.getEvalHistory(skillId!),
        ])

        if (cancelled) return

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
          setEvalRuns(runs.slice(0, 5))
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load skill')
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    void load()
    return () => { cancelled = true }
  }, [skillId])

  async function handleRunEval() {
    if (skillId == null) return
    setRunningEval(true)
    try {
      await api.runEval(skillId)
      // Reload eval history
      const historyData = (await api.getEvalHistory(skillId)) as EvalRun[]
      setEvalRuns(historyData.slice(0, 5))
      // Reload skill for updated eval_score
      const skillData = (await api.getSkill(skillId)) as Skill
      setSkill(skillData)
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

  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <div className="flex items-center gap-3">
          <h1 className="text-lg font-semibold text-gray-900">{skill.name}</h1>
          <Badge variant="outline">v{skill.version}</Badge>
          <Badge variant="secondary">{skill.usage_count} runs</Badge>
          {skill.eval_score != null && (
            <Badge variant={skill.eval_score >= 7 ? 'default' : 'secondary'}>
              {skill.eval_score.toFixed(1)}
            </Badge>
          )}
        </div>
        <p className="mt-1 text-sm text-gray-500">{skill.description}</p>
      </div>

      {/* Steps */}
      {skill.steps && skill.steps.length > 0 && (
        <section>
          <h2 className="text-sm font-semibold text-gray-900">Steps</h2>
          <ol className="mt-2 space-y-2">
            {skill.steps.map((step, i) => (
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
          <div className="mt-2 flex gap-4 text-xs text-gray-400">
            <span>{evalSuite.cases.length} cases</span>
            <span>{evalSuite.runs_count} runs</span>
          </div>
        ) : (
          <p className="mt-2 text-sm text-gray-500">No eval suite configured.</p>
        )}

        {/* Recent runs */}
        {evalRuns.length > 0 && (
          <div className="mt-4 space-y-3">
            <h3 className="text-xs font-medium text-gray-500">Recent Runs</h3>
            {evalRuns.map((run) => (
              <div key={run.id} className="rounded border border-gray-200 bg-white p-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Badge variant={run.score >= 7 ? 'default' : 'secondary'}>
                      {run.score.toFixed(1)}
                    </Badge>
                    <span className="text-xs text-gray-400">
                      {formatDateTime(run.created_at)}
                    </span>
                  </div>
                </div>
                {run.results && run.results.length > 0 && (
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Case</TableHead>
                        <TableHead className="text-right">Result</TableHead>
                        <TableHead>Reason</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {run.results.map((r, i) => (
                        <TableRow key={i}>
                          <TableCell className="text-sm text-gray-900">
                            {r.case_name}
                          </TableCell>
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
                          <TableCell className="max-w-xs truncate text-xs text-gray-400">
                            {r.reason ?? '--'}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                )}
              </div>
            ))}
          </div>
        )}

        {evalRuns.length === 0 && !loading && (
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
