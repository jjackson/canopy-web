import { useCallback, useEffect, useState, type JSX } from 'react'
import { Link, useOutletContext } from 'react-router-dom'
import {
  getNeedsYou,
  listAgentTasks,
  type AgentTaskOut,
  type NeedsYouItem,
  type NeedsYouOut,
  type NeedsYouType,
} from '@/api/agents'
import { decideItem, type ItemDecision } from '@/api/items'
import { runScheduleNow } from '@/api/schedules'
import type { AgentOutletContext } from '@/pages/AgentWorkspacePage'
import { TaskCard } from '@/components/TasksBoard'
import { NEEDS_YOU_BAND, NEEDS_YOU_RANK } from '@/lib/needsYouBands'
import { WorkbenchSubHeader, WorkbenchSkeleton } from 'canopy-ui'

// The three bands, in rank order. Each is a distinct kind of human attention:
// a decision to make (review), an answer Echo is blocked on (question), or an
// FYI with no gate (notify).
//
// Order/label/dot come from lib/needsYouBands, shared with /supervisor's
// WaitingOnYou — that identity is what drifted once (the Review dot rendered a
// different colour on each surface). The blurbs stay here: only this rail shows
// them, so they can't drift.
const BLURBS: Record<NeedsYouType, string> = {
  review: 'Suggestions awaiting your validate / decline',
  question: 'Echo is blocked and needs a decision',
}

const BANDS: { type: NeedsYouType; label: string; blurb: string; dot: string }[] =
  NEEDS_YOU_RANK.map((type) => ({ type, blurb: BLURBS[type], ...NEEDS_YOU_BAND[type] }))

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

// Most items (a posted sync / shipped work product) link OUT to an artifact on
// another host. The schedule nag instead deep-links IN, to the agent's Schedules
// rail where Run now lives — an in-app path must stay an SPA navigation in this
// tab, not a new-tab full page load, so route by url shape.
const isInternal = (url: string): boolean => url.startsWith('/')

function NotifyRow({ item }: { item: NeedsYouItem }): JSX.Element {
  const className =
    'block rounded-lg border border-border bg-card p-3 transition-colors hover:border-primary/40'
  const testId = `needsyou-${item.ref_kind}-${item.ref_id}`
  const body = (
    <>
      <div className="flex items-start gap-2">
        <p className="min-w-0 flex-1 text-[13px] font-semibold leading-snug text-foreground">{item.title}</p>
        {item.url && (
          <span aria-hidden className="shrink-0 text-primary/70">{isInternal(item.url) ? '→' : '↗'}</span>
        )}
      </div>
      {item.subtitle && <p className="mt-1 text-[11px] leading-snug text-muted-foreground">{item.subtitle}</p>}
    </>
  )
  if (item.url && isInternal(item.url)) {
    return (
      <Link to={item.url} data-testid={testId} className={className}>
        {body}
      </Link>
    )
  }
  return (
    <a href={item.url || undefined} target="_blank" rel="noreferrer" data-testid={testId} className={className}>
      {body}
    </a>
  )
}

// A real harness Item that needs a decision — decide it inline (implement / skip /
// defer) instead of bouncing to the Items rail. Closed decision set, same as
// ItemsSection; only `implement` dispatches. A bad dispatch spec 422s and the item
// stays open — we surface that rather than leave the tap looking like it worked.
const ITEM_DECISIONS: ItemDecision[] = ['implement', 'skip', 'defer']

function ItemActionRow({ item, onActed }: { item: NeedsYouItem; onActed: () => void }): JSX.Element {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  return (
    <article
      data-testid={`needsyou-item-${item.ref_id}`}
      className="rounded-lg border border-border bg-card p-3"
    >
      <p className="text-[13px] font-semibold leading-snug text-foreground">{item.title}</p>
      {item.subtitle && <p className="mt-1 text-[11px] leading-snug text-muted-foreground">{item.subtitle}</p>}
      {error && <p className="mt-1 text-[11px] text-destructive">{error}</p>}
      <div className="mt-2 flex flex-wrap gap-2">
        {ITEM_DECISIONS.map((d) => (
          <button
            key={d}
            type="button"
            disabled={busy}
            onClick={async () => {
              setBusy(true)
              setError(null)
              try {
                await decideItem(String(item.ref_id), d)
                onActed()
              } catch (e: unknown) {
                setError(e instanceof Error ? e.message : 'Failed to decide')
              } finally {
                setBusy(false)
              }
            }}
            className="rounded-md border border-border px-3 py-1 text-[12px] capitalize text-foreground transition-colors hover:bg-muted disabled:opacity-50"
          >
            {d}
          </button>
        ))}
      </div>
    </article>
  )
}

// The unattended-schedule nag — fire the occurrence off-cycle right here (Run now),
// instead of deep-linking out to the Schedules rail to find the same button.
function ScheduleNagRow({
  slug,
  item,
  onActed,
}: {
  slug: string
  item: NeedsYouItem
  onActed: () => void
}): JSX.Element {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  return (
    <article
      data-testid={`needsyou-schedule-${item.ref_id}`}
      className="rounded-lg border border-border bg-card p-3"
    >
      <div className="flex items-start gap-2">
        <div className="min-w-0 flex-1">
          <p className="text-[13px] font-semibold leading-snug text-foreground">{item.title}</p>
          {item.subtitle && (
            <p className="mt-1 text-[11px] leading-snug text-muted-foreground">{item.subtitle}</p>
          )}
        </div>
        <button
          type="button"
          disabled={busy}
          onClick={async () => {
            setBusy(true)
            setError(null)
            try {
              await runScheduleNow(slug, Number(item.ref_id))
              onActed()
            } catch (e: unknown) {
              setError(e instanceof Error ? e.message : 'Failed to run')
            } finally {
              setBusy(false)
            }
          }}
          className="shrink-0 rounded-md border border-border px-3 py-1 text-[12px] text-foreground transition-colors hover:bg-muted disabled:opacity-50"
        >
          {busy ? 'Starting…' : 'Run now'}
        </button>
      </div>
      {error && <p className="mt-1 text-[11px] text-destructive">{error}</p>}
    </article>
  )
}

function Band({
  type,
  label,
  blurb,
  dot,
  items,
  tasksById,
  slug,
  reload,
}: {
  type: NeedsYouType
  label: string
  blurb: string
  dot: string
  items: NeedsYouItem[]
  tasksById: Map<number, AgentTaskOut>
  slug: string
  reload: () => void
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
        {mine.map((i) => {
          // Task items render the SAME actionable board card — you accept /
          // decline / dispatch right here, no bounce to the board.
          if (i.ref_kind === 'task') {
            // ref_id widened to `number | string` when Items joined the inbox
            // (their pk is a UUID). TS can't narrow it from ref_kind — the two
            // fields are independent — but a task's ref_id is always its int pk,
            // so coerce at this boundary rather than union the map's key type.
            const task = tasksById.get(Number(i.ref_id))
            if (!task) return null
            return (
              <div key={`task-${i.ref_id}`} data-testid={`needsyou-task-${i.ref_id}`}>
                <TaskCard task={task} onChanged={reload} />
              </div>
            )
          }
          // Real Items decide inline; schedule nags fire inline — the two review/
          // question kinds that were dead links before. Everything else (sync,
          // work product, run gate) still links out to its artifact/review surface.
          if (i.ref_kind === 'item') {
            return <ItemActionRow key={`item-${i.ref_id}`} item={i} onActed={reload} />
          }
          if (i.ref_kind === 'schedule') {
            return <ScheduleNagRow key={`schedule-${i.ref_id}`} slug={slug} item={i} onActed={reload} />
          }
          return <NotifyRow key={`${i.ref_kind}-${i.ref_id}`} item={i} />
        })}
      </div>
    </section>
  )
}

/**
 * The supervisor's home screen: "what does Echo need from me right now?" in one
 * scan. Renders the actionable board card for each task that needs you (act
 * inline — accept/decline/dispatch — without bouncing to the board), plus
 * link-out rows for FYI items. Ranked Review → Question → Notify. Consumes
 * GET /api/agents/{slug}/needs-you (the durable shape CLI agents query too) +
 * the full tasks so the cards are fully actionable.
 */
export function NeedsYouSection() {
  const { agent } = useOutletContext<AgentOutletContext>()
  const [data, setData] = useState<NeedsYouOut | null>(null)
  const [tasks, setTasks] = useState<AgentTaskOut[]>([])

  const reload = useCallback(() => {
    void Promise.all([getNeedsYou(agent.slug), listAgentTasks(agent.slug)])
      .then(([d, t]) => {
        setData(d)
        setTasks(t)
      })
      .catch(() => {
        setData({ agent_slug: agent.slug, waiting_count: 0, items: [] })
        setTasks([])
      })
  }, [agent.slug])

  useEffect(() => {
    setData(null)
    reload()
  }, [agent.slug, reload])

  const tasksById = new Map(tasks.map((t) => [t.id, t]))

  return (
    <div className="max-w-4xl px-6 py-8">
      <WorkbenchSubHeader
        title="Needs you"
        action={data && data.waiting_count > 0 ? <WaitingBadge count={data.waiting_count} /> : undefined}
      />
      {data === null ? (
        <WorkbenchSkeleton />
      ) : (data.items ?? []).length === 0 ? (
        <p className="text-[13px] text-muted-foreground">
          Nothing needs you right now — Echo has the ball.
        </p>
      ) : (
        <div className="space-y-7">
          {BANDS.map((b) => (
            <Band
              key={b.type}
              {...b}
              items={[...(data.items ?? [])]}
              tasksById={tasksById}
              slug={agent.slug}
              reload={reload}
            />
          ))}
        </div>
      )}
    </div>
  )
}
