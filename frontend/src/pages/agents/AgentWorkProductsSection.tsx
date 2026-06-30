import { useEffect, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import { listAgentWorkProducts, type AgentWorkProductOut } from '@/api/agents'
import type { AgentOutletContext } from '@/pages/AgentWorkspacePage'
import { WorkProductCard } from '@/components/agents/cards'
import { WorkbenchSubHeader, WorkbenchSkeleton } from 'canopy-ui'

export function AgentWorkProductsSection() {
  const { agent } = useOutletContext<AgentOutletContext>()
  const [items, setItems] = useState<AgentWorkProductOut[] | null>(null)

  useEffect(() => {
    let cancelled = false
    setItems(null)
    listAgentWorkProducts(agent.slug, { limit: 200 })
      .then((page) => !cancelled && setItems(page.items))
      .catch(() => !cancelled && setItems([]))
    return () => {
      cancelled = true
    }
  }, [agent.slug])

  return (
    <div className="max-w-4xl px-6 py-8">
      <WorkbenchSubHeader title="Work products" count={items?.length} />
      {items === null ? (
        <WorkbenchSkeleton />
      ) : items.length === 0 ? (
        <p className="text-[13px] text-muted-foreground">No work products yet.</p>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {items.map((wp) => (
            <WorkProductCard key={wp.id} wp={wp} />
          ))}
        </div>
      )}
    </div>
  )
}
