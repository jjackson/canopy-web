import type { JSX } from 'react'
import type { FleetNeedsYouOut, NeedsYouItem, NeedsYouType } from '@/api/agents'

// Cross-fleet "waiting on you" — the React counterpart of menubar.py's section
// (menubar.py:427). Ranked exactly as the server ranks it: review, then
// question, then notify. Read-only for now: rows link out. Acting on an item
// inline is Phase 3, with the composer.
const RANK: NeedsYouType[] = ['review', 'question', 'notify']

const BAND: Record<NeedsYouType, { label: string; dot: string }> = {
  review: { label: 'Review', dot: 'bg-info' },
  question: { label: 'Question', dot: 'bg-warning' },
  notify: { label: 'Notify', dot: 'bg-primary/50' },
}

type Row = NeedsYouItem & { agent_slug: string }

function ItemRow({ item }: { item: Row }): JSX.Element {
  const body = (
    <>
      <div className="flex items-start gap-2">
        <p className="min-w-0 flex-1 text-[13px] font-semibold leading-snug text-foreground">{item.title}</p>
        {item.url && <span aria-hidden className="shrink-0 text-primary/70">↗</span>}
      </div>
      <p className="mt-1 text-[11px] text-muted-foreground">
        {item.agent_slug}
        {item.subtitle ? ` · ${item.subtitle}` : ''}
      </p>
    </>
  )
  const cls = 'block rounded-lg border border-border bg-card p-3 transition-colors hover:border-primary/40'
  return item.url ? (
    <a href={item.url} target="_blank" rel="noreferrer" className={cls} data-testid={`waiting-${item.ref_kind}-${item.ref_id}`}>
      {body}
    </a>
  ) : (
    <div className={cls} data-testid={`waiting-${item.ref_kind}-${item.ref_id}`}>{body}</div>
  )
}

export function WaitingOnYou({ fleet }: { fleet: FleetNeedsYouOut }): JSX.Element {
  // Flatten agent-grouped blocks into one cross-fleet list, tagging each row
  // with its agent — on a phone the ranked queue matters more than the grouping.
  const rows: Row[] = (fleet.agents ?? []).flatMap((block) =>
    (block.items ?? []).map((item) => ({ ...item, agent_slug: block.agent_slug })),
  )

  if (rows.length === 0) {
    return (
      <p className="rounded-lg border border-border bg-card p-3 text-[13px] text-muted-foreground" data-testid="waiting-empty">
        Nothing waiting on you.
      </p>
    )
  }

  return (
    <div className="flex flex-col gap-3" data-testid="waiting-on-you">
      {RANK.map((type) => {
        const band = rows.filter((r) => r.type === type)
        if (band.length === 0) return null
        return (
          <section key={type}>
            <div className="mb-1.5 flex items-center gap-1.5">
              <span className={`h-1.5 w-1.5 rounded-full ${BAND[type].dot}`} />
              <h3 className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                {BAND[type].label}
              </h3>
              <span className="text-[11px] text-foreground-subtle">{band.length}</span>
            </div>
            <div className="flex flex-col gap-2">
              {band.map((r) => (
                <ItemRow key={`${r.agent_slug}-${r.ref_kind}-${r.ref_id}`} item={r} />
              ))}
            </div>
          </section>
        )
      })}
    </div>
  )
}
