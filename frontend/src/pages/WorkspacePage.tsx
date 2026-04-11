import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { api } from '@/api/client'
import { useWorkspaceStore } from '@/store/workspaceSlice'
import { StepIndicator } from '@/components/Workspace/StepIndicator'
import { SourcePanel } from '@/components/Workspace/SourcePanel'
import { ApproachPanel } from '@/components/Workspace/ApproachPanel'
import { EvalPanel } from '@/components/Workspace/EvalPanel'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'

/** Map session status string to step indicator index */
function statusToStep(status: string): number {
  switch (status) {
    case 'created':
    case 'analyzing':
      return 0
    case 'proposed':
      return 1
    case 'editing':
      return 2
    case 'testing':
      return 3
    case 'published':
      return 4
    default:
      return 0
  }
}

interface WorkspaceData {
  id?: number
  collection_id?: number
  status?: string
  proposed_approach?: Record<string, unknown> | null
  proposed_eval_cases?: Record<string, unknown>[]
  skill_draft?: Record<string, unknown> | null
}

interface CollectionData {
  sources?: Record<string, unknown>[]
}

export function WorkspacePage() {
  const { sessionId: sessionIdParam } = useParams<{ sessionId: string }>()
  const navigate = useNavigate()
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [publishing, setPublishing] = useState(false)

  const {
    status,
    approach,
    evalCases,
    streamingText,
    isStreaming,
    sources,
    setSession,
    setStatus,
    setApproach,
    setEvalCases,
    setSkillDraft,
    setSources,
    reset,
  } = useWorkspaceStore()

  const sessionId = sessionIdParam ? Number(sessionIdParam) : null

  useEffect(() => {
    if (sessionId == null || isNaN(sessionId)) {
      setError('Invalid session ID')
      setLoading(false)
      return
    }

    reset()
    setSession(sessionId)

    let cancelled = false
    let pollTimer: ReturnType<typeof setTimeout> | null = null

    async function load() {
      try {
        const workspace = (await api.getWorkspace(sessionId!)) as WorkspaceData

        if (cancelled) return

        setStatus(workspace.status ?? '')
        if (workspace.proposed_approach) setApproach(workspace.proposed_approach)
        if (workspace.proposed_eval_cases) setEvalCases(workspace.proposed_eval_cases)
        if (workspace.skill_draft) setSkillDraft(workspace.skill_draft)

        // Load sources from collection
        if (workspace.collection_id) {
          try {
            const collection = (await api.getCollection(
              workspace.collection_id
            )) as CollectionData
            if (!cancelled && collection.sources) {
              setSources(collection.sources)
            }
          } catch {
            // Sources loading is non-critical
          }
        }

        // If still analyzing, poll for updates
        if (workspace.status === 'created' || workspace.status === 'analyzing') {
          pollTimer = setTimeout(() => {
            if (!cancelled) void load()
          }, 2000)
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load workspace')
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    void load()

    return () => {
      cancelled = true
      if (pollTimer) clearTimeout(pollTimer)
    }
  }, [sessionId, reset, setSession, setStatus, setApproach, setEvalCases, setSkillDraft, setSources])

  async function handlePublish() {
    if (sessionId == null) return
    setPublishing(true)
    try {
      const result = (await api.publishSkill(sessionId)) as { skill_id?: number }
      if (result.skill_id) {
        navigate(`/skills/${result.skill_id}`)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Publish failed')
    } finally {
      setPublishing(false)
    }
  }

  if (loading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-6 w-64" />
        <div className="flex gap-4">
          <Skeleton className="h-96 w-1/3" />
          <Skeleton className="h-96 flex-1" />
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="rounded-lg border border-red-400/30 bg-red-400/10 p-4 text-sm text-red-400">
        {error}
      </div>
    )
  }

  const currentStep = statusToStep(status)

  return (
    <div className="flex h-[calc(100vh-5rem)] flex-col rounded-xl border border-stone-800 bg-stone-900 overflow-hidden">
      {/* Step indicator */}
      <div className="shrink-0 border-b border-stone-800 bg-stone-950 px-4 py-2.5">
        <StepIndicator currentStep={currentStep} />
      </div>

      {/* Main content: 30/70 split */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left: Sources (30%) */}
        <div className="w-[30%] min-w-0 shrink-0 border-r border-stone-800">
          <SourcePanel sources={sources} />
        </div>

        {/* Right: Approach + Eval + Actions (70%) */}
        <div className="flex flex-1 min-w-0 flex-col overflow-hidden">
          {/* Approach — scrollable */}
          <div className="flex-1 overflow-y-auto bg-stone-900">
            <ApproachPanel
              approach={approach as Record<string, unknown> & { name?: string; description?: string; steps?: { name?: string; description?: string; tools?: string[] }[] } | null}
              streamingText={streamingText}
              isStreaming={isStreaming}
            />
          </div>

          {/* Eval cases — collapsible */}
          <EvalPanel evalCases={evalCases as { name?: string; input?: string | Record<string, unknown>; expected?: string | Record<string, unknown>; expected_output?: string | Record<string, unknown> }[]} />

          {/* Action bar */}
          <div className="shrink-0 border-t border-stone-800 bg-stone-950 px-4 py-2.5 flex items-center justify-end gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={currentStep < 1}
            >
              Run Eval
            </Button>
            <Button
              size="sm"
              onClick={() => void handlePublish()}
              disabled={publishing || currentStep < 2}
            >
              {publishing ? 'Publishing...' : 'Publish'}
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}
