import type { JSX } from 'react'
import type { ItemOut } from '@/api/items'
import { ITEM_BAND as BAND, ITEM_KIND_RANK as RANK, type ItemKind } from '@/lib/itemBands'
import { ItemCard } from '@/components/items/ItemCard'

// The fleet's "waiting on you" queue — every OPEN item across the agents you can
// see, flattened into one ranked list (Review, then Question). On a phone the
// ranked queue matters more than per-agent grouping, so each row is tagged with
// its agent instead. Fully actionable in place via ItemCard — no linking out.

export function ItemInbox({ items, onActed }: { items: ItemOut[]; onActed: () => void }): JSX.Element {
  if (items.length === 0) {
    return (
      <p
        className="rounded-lg border border-border bg-card p-3 text-[13px] text-muted-foreground"
        data-testid="inbox-empty"
      >
        Nothing waiting on you.
      </p>
    )
  }

  return (
    <div className="flex flex-col gap-3" data-testid="item-inbox">
      {RANK.map((kind: ItemKind) => {
        const band = items.filter((i) => i.kind === kind)
        if (band.length === 0) return null
        return (
          <section key={kind}>
            <div className="mb-1.5 flex items-center gap-1.5">
              <span className={`h-1.5 w-1.5 rounded-full ${BAND[kind].dot}`} />
              <h3 className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                {BAND[kind].label}
              </h3>
              <span className="text-[11px] text-foreground-subtle">{band.length}</span>
            </div>
            <div className="flex flex-col gap-2">
              {band.map((item) => (
                <ItemCard key={item.id} item={item} onActed={onActed} showAgent />
              ))}
            </div>
          </section>
        )
      })}
    </div>
  )
}
