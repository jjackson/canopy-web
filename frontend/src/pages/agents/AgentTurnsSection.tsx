import { useEffect, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import { listAgentTurns, type AgentTurnOut } from '@/api/agents'
import type { AgentOutletContext } from '@/pages/AgentWorkspacePage'
import { TurnCard } from '@/components/agents/cards'
import { WorkbenchSubHeader, WorkbenchSkeleton } from 'canopy-ui'

export function AgentTurnsSection() {
  const { agent } = useOutletContext<AgentOutletContext>()
  const [turns, setTurns] = useState<AgentTurnOut[] | null>(null)

  useEffect(() => {
    let cancelled = false
    setTurns(null)
    listAgentTurns(agent.slug, { limit: 200 })
      .then((page) => !cancelled && setTurns(page.items))
      .catch(() => !cancelled && setTurns([]))
    return () => {
      cancelled = true
    }
  }, [agent.slug])

  return (
    <div className="max-w-4xl px-6 py-8">
      <WorkbenchSubHeader title="Turns" count={turns?.length} />
      {turns === null ? (
        <WorkbenchSkeleton />
      ) : turns.length === 0 ? (
        <p className="text-[13px] text-muted-foreground">
          No turns yet. A packaged turn records the request it advanced, what the agent did, the
          deliverables — and, optionally, a link to the session transcript.
        </p>
      ) : (
        <div className="space-y-3">
          {turns.map((t) => (
            <TurnCard key={t.id} turn={t} />
          ))}
        </div>
      )}
    </div>
  )
}
