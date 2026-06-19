import { useEffect, useState, type JSX } from 'react'
import { Link, useOutletContext } from 'react-router-dom'
import { getNeedsYou, type NeedsYouItem, type NeedsYouOut, type NeedsYouType } from '@/api/agents'
import type { AgentOutletContext } from '@/pages/AgentWorkspacePage'
import { WorkbenchSubHeader, WorkbenchSkeleton } from '@canopy/workbench'

// The three bands, in rank order. Each is a distinct kind of human attention:
// a decision to make (review), an answer Echo is blocked on (question), or an
// FYI with no gate (notify).
const BANDS: { type: NeedsYouType; label: string; blurb: string; dot: string }[] = [
  { type: 'review', label: 'Review', blurb: 'Suggestions awaiting your validate / decline', dot: 'bg-muted-foreground' },
  { type: 'question', label: 'Question', blurb: 'Echo is blocked and needs a decision', dot: 'bg-amber-400' },
  { type: 'notify', label: 'Notify', blurb: 'Recent work — no action needed', dot: 'bg-primary/50' },
]

// The "N waiting on you" badge — mirrors the board's "N queued for Echo".
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

function ItemRow({ item }: { item: NeedsYouItem }): JSX.Element {
  const isTask = item.ref_kind === 'task'
  // Task items route to the board where the human can act; FYI items link out
  // to the artifact (the doc / work product) directly.
  const inner = (
    <>
      <div className="flex items-start gap-2">
        <p className="min-w-0 flex-1 text-[13px] font-semibold leading-snug text-foreground">
          {item.title}
        </p>
        {!isTask && item.url && <span aria-hidden className="shrink-0 text-primary/70">↗</span>}
      </div>
      {item.subtitle && (
        <p className="mt-1 text-[11px] leading-snug text-muted-foreground">{item.subtitle}</p>
      )}
      {isTask && item.url && (
        <span className="mt-1.5 inline-flex items-center gap-1 text-[10px] font-medium text-muted-foreground">
          source <span className="text-primary/70">↗</span>
        </span>
      )}
    </>
  )

  const className =
    'block rounded-lg border border-border bg-card p-3 text-left transition-colors hover:border-primary/40'

  if (isTask) {
    return (
      <Link to="../tasks" data-testid={`needsyou-${item.ref_kind}-${item.ref_id}`} className={className}>
        {inner}
      </Link>
    )
  }
  return (
    <a
      href={item.url || undefined}
      target="_blank"
      rel="noreferrer"
      data-testid={`needsyou-${item.ref_kind}-${item.ref_id}`}
      className={className}
    >
      {inner}
    </a>
  )
}

function Band({
  type,
  label,
  blurb,
  dot,
  items,
}: {
  type: NeedsYouType
  label: string
  blurb: string
  dot: string
  items: NeedsYouItem[]
}): JSX.Element | null {
  const mine = items.filter((i) => i.type === type)
  if (mine.length === 0) return null
  return (
    <section data-testid={`needsyou-band-${type}`}>
      <div className="mb-2 flex items-center gap-2 border-b border-border pb-1.5">
        <span className={`h-1.5 w-1.5 rounded-full ${dot}`} />
        <span className="text-[11px] font-bold uppercase tracking-[0.06em] text-foreground">{label}</span>
        <span className="text-[11px] text-muted-foreground">{blurb}</span>
        <span className="ml-auto text-[11px] text-muted-foreground">{mine.length}</span>
      </div>
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        {mine.map((i) => (
          <ItemRow key={`${i.ref_kind}-${i.ref_id}`} item={i} />
        ))}
      </div>
    </section>
  )
}

/**
 * The supervisor's home screen: "what does Echo need from me right now?" in one
 * scan. Aggregates the human-actionable items across the board, typed and
 * ranked Review → Question → Notify. Consumes GET /api/agents/{slug}/needs-you
 * (the durable shape CLI agents query too).
 */
export function NeedsYouSection() {
  const { agent } = useOutletContext<AgentOutletContext>()
  const [data, setData] = useState<NeedsYouOut | null>(null)

  useEffect(() => {
    let cancelled = false
    setData(null)
    getNeedsYou(agent.slug)
      .then((d) => !cancelled && setData(d))
      .catch(() => !cancelled && setData({ agent_slug: agent.slug, waiting_count: 0, items: [] }))
    return () => {
      cancelled = true
    }
  }, [agent.slug])

  return (
    <div className="max-w-4xl px-6 py-8">
      <WorkbenchSubHeader
        title="Needs you"
        action={data && data.waiting_count > 0 ? <WaitingBadge count={data.waiting_count} /> : undefined}
      />
      {data === null ? (
        <WorkbenchSkeleton />
      ) : data.items.length === 0 ? (
        <p className="text-[13px] text-muted-foreground">
          Nothing needs you right now — Echo has the ball.
        </p>
      ) : (
        <div className="space-y-7">
          {BANDS.map((b) => (
            <Band key={b.type} {...b} items={data.items} />
          ))}
        </div>
      )}
    </div>
  )
}
