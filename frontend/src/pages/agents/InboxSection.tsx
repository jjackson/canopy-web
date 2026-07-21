import { useCallback, useEffect, useState, type JSX } from 'react'
import { useOutletContext } from 'react-router-dom'
import { listItems, type ItemOut } from '@/api/items'
import type { AgentOutletContext } from '@/pages/AgentWorkspacePage'
import { ITEM_BAND, ITEM_KIND_RANK, type ItemKind } from '@/lib/itemBands'
import { ItemCard } from '@/components/items/ItemCard'
import { WorkbenchSubHeader, WorkbenchSkeleton } from 'canopy-ui'

// One agent's inbox: its OPEN items, ranked Review -> Question, each decidable in
// place. This is the per-agent counterpart of /supervisor's fleet ItemInbox; both
// render the same actionable ItemCard and share band identity (lib/itemBands), so
// they can't drift. The inbox is a pure query over items now — no projections.

// The "N waiting on you" badge — mirrors the board's "N queued".
function WaitingBadge({ count }: { count: number }): JSX.Element {
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded border border-primary/30 bg-primary/10 px-2 py-0.5 text-[11px] font-medium text-primary"
      title="Items waiting on you to act"
    >
      <span className="h-1.5 w-1.5 rounded-full bg-primary" />
      {count} waiting on you
    </span>
  )
}

function Band({
  kind,
  items,
  reload,
}: {
  kind: ItemKind
  items: ItemOut[]
  reload: () => void
}): JSX.Element | null {
  const mine = items.filter((i) => i.kind === kind)
  if (mine.length === 0) return null
  const { label, blurb, dot } = ITEM_BAND[kind]
  return (
    <section data-testid={`inbox-band-${kind}`}>
      <div className="mb-2 flex items-center gap-2 border-b border-border pb-1.5">
        <span className={`h-1.5 w-1.5 rounded-full ${dot}`} />
        <span className="text-[11px] font-bold uppercase tracking-[0.06em] text-foreground">{label}</span>
        <span className="text-[11px] text-muted-foreground">{blurb}</span>
        <span className="ml-auto text-[11px] text-muted-foreground">{mine.length}</span>
      </div>
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        {mine.map((item) => (
          <ItemCard key={item.id} item={item} onActed={reload} />
        ))}
      </div>
    </section>
  )
}

/**
 * The agent's inbox: "what does this agent need from me right now?" in one scan,
 * decidable inline. Consumes GET /api/agents/{slug}/items/?state=open.
 */
export function InboxSection() {
  const { agent } = useOutletContext<AgentOutletContext>()
  const [items, setItems] = useState<ItemOut[] | null>(null)

  const reload = useCallback(() => {
    void listItems(agent.slug, { state: 'open' })
      .then(setItems)
      .catch(() => setItems([]))
  }, [agent.slug])

  useEffect(() => {
    setItems(null)
    reload()
  }, [agent.slug, reload])

  const count = items?.length ?? 0

  return (
    <div className="max-w-4xl px-6 py-8">
      <WorkbenchSubHeader
        title="Inbox"
        action={count > 0 ? <WaitingBadge count={count} /> : undefined}
      />
      {items === null ? (
        <WorkbenchSkeleton />
      ) : items.length === 0 ? (
        <p className="text-[13px] text-muted-foreground">
          Nothing needs you right now — {agent.name} has the ball.
        </p>
      ) : (
        <div className="space-y-7">
          {ITEM_KIND_RANK.map((kind) => (
            <Band key={kind} kind={kind} items={items} reload={reload} />
          ))}
        </div>
      )}
    </div>
  )
}
