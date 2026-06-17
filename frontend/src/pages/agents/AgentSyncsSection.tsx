import { useEffect, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import { listAgentSyncs, type AgentSyncOut } from '@/api/agents'
import type { AgentOutletContext } from '@/pages/AgentWorkspacePage'
import { SyncCard } from '@/components/agents/cards'
import { SectionSubHeader, SectionSkeleton } from '@/components/agents/SectionSubHeader'

export function AgentSyncsSection() {
  const { agent } = useOutletContext<AgentOutletContext>()
  const [syncs, setSyncs] = useState<AgentSyncOut[] | null>(null)

  useEffect(() => {
    let cancelled = false
    setSyncs(null)
    listAgentSyncs(agent.slug, { limit: 200 })
      .then((page) => !cancelled && setSyncs(page.items))
      .catch(() => !cancelled && setSyncs([]))
    return () => {
      cancelled = true
    }
  }, [agent.slug])

  return (
    <div className="max-w-4xl px-6 py-8">
      <SectionSubHeader title="Syncs" count={syncs?.length} />
      {syncs === null ? (
        <SectionSkeleton />
      ) : syncs.length === 0 ? (
        <p className="text-[13px] text-stone-600">No syncs yet.</p>
      ) : (
        <div className="space-y-3">
          {syncs.map((s) => (
            <SyncCard key={s.id} sync={s} />
          ))}
        </div>
      )}
    </div>
  )
}
