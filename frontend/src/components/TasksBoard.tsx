import { useState, type JSX, type ReactNode } from 'react'
import {
  postTaskCommand,
  type AgentCommandKind,
  type AgentTaskOut,
} from '@/api/agents'

// ── "Who has the ball" model ───────────────────────────────────────────────
// The board is organized by whose court the next action sits in, not by equal
// status columns. `assigned` names who the next step waits on: the agent
// ("Echo") or a human. Empty or case-insensitive 'echo' means the agent.

function isEcho(assigned: string): boolean {
  const a = (assigned || '').trim().toLowerCase()
  return a === '' || a === 'echo'
}

function headline(task: AgentTaskOut): string {
  return (task.next_action || '').trim() || (task.title || '').trim()
}

function formatDue(s: string): string {
  return new Date(s).toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
  })
}

function isPastDue(due: string): boolean {
  const d = new Date(due)
  if (Number.isNaN(d.getTime())) return false
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  return d.getTime() < today.getTime()
}

// ── Small primitives ────────────────────────────────────────────────────────

// confidence: 'high' = solid dot, 'low' = hollow/hatched, '' = nothing.
function ConfidenceDot({ confidence }: { confidence: string }): JSX.Element | null {
  const c = (confidence || '').trim().toLowerCase()
  if (c === 'high') {
    return (
      <span
        className="h-2 w-2 shrink-0 rounded-full bg-primary"
        title="High confidence"
        aria-label="High confidence"
      />
    )
  }
  if (c === 'low') {
    return (
      <span
        className="h-2 w-2 shrink-0 rounded-full border border-dashed border-muted-foreground/70"
        title="Low confidence"
        aria-label="Low confidence"
      />
    )
  }
  return null
}

// The "ball is in the agent's court" affordance: Echo + a pulsing dot.
function EchoWorking(): JSX.Element {
  return (
    <span className="inline-flex items-center gap-1.5 text-[11px] font-medium text-primary">
      <span className="relative flex h-2 w-2">
        <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-primary/60" />
        <span className="relative inline-flex h-2 w-2 rounded-full bg-primary" />
      </span>
      Echo
    </span>
  )
}

// The "ball is in a human's court" affordance: an amber waiting chip.
function WaitingChip({ who }: { who: string }): JSX.Element {
  return (
    <span className="inline-flex items-center gap-1 rounded border border-amber-500/30 bg-amber-500/15 px-1.5 py-0.5 text-[11px] font-medium text-amber-300">
      Waiting on {who}
    </span>
  )
}

function OwnerTag({ owner }: { owner: string }): JSX.Element | null {
  const o = (owner || '').trim()
  if (!o) return null
  return (
    <span className="text-[10px] text-muted-foreground" title={`Owner: ${o}`}>
      Owner · {o}
    </span>
  )
}

function DueChip({ due, done }: { due: string; done: boolean }): JSX.Element {
  const pastDue = !done && isPastDue(due)
  return (
    <span
      className={`inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-[10px] ${
        pastDue
          ? 'border-destructive/40 bg-destructive/10 text-destructive'
          : 'border-border bg-muted text-muted-foreground'
      }`}
      title={pastDue ? 'Past due' : undefined}
    >
      {pastDue && <span aria-hidden>⚠</span>}
      {formatDue(due)}
    </span>
  )
}

function TaskLinkChip({ label, url }: { label: string; url: string }): JSX.Element | null {
  if (!url) return null
  return (
    <a
      href={url}
      target="_blank"
      rel="noreferrer"
      className="inline-flex items-center gap-1 rounded border border-border bg-muted px-2 py-0.5 text-[10px] font-medium text-muted-foreground transition-colors hover:border-primary/50 hover:text-primary"
    >
      <span className="text-primary/70">↗</span>
      {label || url}
    </a>
  )
}

// A "source ↗" chip linking the originating thread/doc.
function SourceChip({ url }: { url: string }): JSX.Element | null {
  if (!url || !url.trim()) return null
  return (
    <a
      href={url}
      target="_blank"
      rel="noreferrer"
      className="inline-flex items-center gap-1 rounded border border-border bg-muted px-2 py-0.5 text-[10px] font-medium text-muted-foreground transition-colors hover:border-primary/50 hover:text-primary"
      title={url}
    >
      source <span className="text-primary/70">↗</span>
    </a>
  )
}

// A muted "Why: …" rationale line — expandable when long. Lets a human validate
// a suggested task before accepting it.
function RationaleLine({ rationale }: { rationale: string }): JSX.Element | null {
  const text = (rationale || '').trim()
  const [expanded, setExpanded] = useState(false)
  if (!text) return null
  const long = text.length > 120
  return (
    <p className="mt-1.5 text-[11px] leading-snug text-muted-foreground/90">
      <span className="text-muted-foreground/70">Why: </span>
      {long && !expanded ? `${text.slice(0, 120).trimEnd()}…` : text}
      {long && (
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="ml-1 text-primary/80 hover:text-primary"
        >
          {expanded ? 'less' : 'more'}
        </button>
      )}
    </p>
  )
}

// ── Actions ──────────────────────────────────────────────────────────────────
// Secondary, muted affordances that POST a command to the queue. Deliberately
// quieter than the next-action headline.

// A small text button used for muted in-card actions.
function ActionButton({
  children,
  onClick,
  disabled,
  tone = 'muted',
}: {
  children: ReactNode
  onClick: () => void
  disabled?: boolean
  tone?: 'muted' | 'primary' | 'destructive'
}): JSX.Element {
  const toneClass =
    tone === 'primary'
      ? 'text-primary hover:text-primary/80'
      : tone === 'destructive'
        ? 'text-destructive/90 hover:text-destructive'
        : 'text-muted-foreground hover:text-foreground'
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={`text-[11px] font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${toneClass}`}
    >
      {children}
    </button>
  )
}

// Hosts a card's command-posting state: in-flight lock, error surfacing, and a
// decline reason input. Renders the actions appropriate to the task's status.
function TaskActions({
  task,
  onChanged,
}: {
  task: AgentTaskOut
  onChanged?: () => void
}): JSX.Element | null {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [declining, setDeclining] = useState(false)
  const [reason, setReason] = useState('')

  async function run(kind: AgentCommandKind, payload?: Record<string, unknown>) {
    if (busy) return
    setBusy(true)
    setError(null)
    try {
      await postTaskCommand(task.agent_slug, task.id, kind, payload)
      onChanged?.()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Action failed')
      setBusy(false)
    }
    // On success we leave `busy` true: the board is about to refetch and this
    // card will be replaced, so re-enabling would only flash.
  }

  const isSuggested = task.status === 'suggested'
  const isInProgress = task.status === 'in_progress'
  if (!isSuggested && !isInProgress) return null

  return (
    <div className="mt-2.5 border-t border-border/60 pt-2">
      {isSuggested && !declining && (
        <div className="flex items-center gap-3">
          <ActionButton tone="primary" disabled={busy} onClick={() => run('accept')}>
            Accept
          </ActionButton>
          <ActionButton
            tone="muted"
            disabled={busy}
            onClick={() => {
              setError(null)
              setDeclining(true)
            }}
          >
            Decline
          </ActionButton>
        </div>
      )}

      {isSuggested && declining && (
        <div className="flex flex-wrap items-center gap-2">
          <input
            type="text"
            autoFocus
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="Reason (optional)"
            disabled={busy}
            className="h-7 min-w-0 flex-1 rounded border border-border bg-muted px-2 text-[11px] text-foreground outline-none placeholder:text-muted-foreground/60 focus:border-primary/50"
            onKeyDown={(e) => {
              if (e.key === 'Enter') run('decline', { reason: reason.trim() })
              if (e.key === 'Escape') setDeclining(false)
            }}
          />
          <ActionButton
            tone="destructive"
            disabled={busy}
            onClick={() => run('decline', { reason: reason.trim() })}
          >
            Confirm decline
          </ActionButton>
          <ActionButton tone="muted" disabled={busy} onClick={() => setDeclining(false)}>
            Cancel
          </ActionButton>
        </div>
      )}

      {isInProgress && (
        <div className="flex items-center gap-3">
          <ActionButton tone="primary" disabled={busy} onClick={() => run('dispatch')}>
            Echo, do this now
          </ActionButton>
          <ActionButton tone="muted" disabled={busy} onClick={() => run('done')}>
            Mark done
          </ActionButton>
        </div>
      )}

      {error && <p className="mt-1.5 text-[10px] text-destructive">{error}</p>}
    </div>
  )
}

// ── Card ────────────────────────────────────────────────────────────────────

function TaskCard({
  task,
  onChanged,
}: {
  task: AgentTaskOut
  onChanged?: () => void
}): JSX.Element {
  const head = headline(task)
  const outcome = (task.title || '').trim()
  const showOutcome = outcome && outcome !== head
  const echo = isEcho(task.assigned)
  const isSuggested = task.status === 'suggested'
  const isDone = task.status === 'done'

  return (
    <div className="rounded-lg border border-border bg-card p-3 transition-colors hover:border-primary/40">
      <div className="flex items-start gap-2">
        {isSuggested && <ConfidenceDot confidence={task.confidence} />}
        <p className="min-w-0 flex-1 text-[13px] font-semibold leading-snug text-foreground">
          {head}
        </p>
      </div>

      {/* Whose court: the single ball signal — Echo working, or waiting on a human. */}
      {!isSuggested && !isDone && task.status === 'in_progress' && (
        <div className="mt-1.5">
          {echo ? <EchoWorking /> : <WaitingChip who={task.assigned.trim()} />}
        </div>
      )}

      {/* Secondary line: the outcome, only when it differs from the headline. */}
      {showOutcome && (
        <p className="mt-1.5 text-[11px] leading-snug text-muted-foreground">{outcome}</p>
      )}

      {/* Context: why this is here (esp. for validating suggested tasks). */}
      <RationaleLine rationale={task.rationale} />

      {(task.owner ||
        task.due ||
        task.source_url ||
        (task.links && task.links.length > 0)) && (
        <div className="mt-2 flex flex-wrap items-center gap-1.5">
          <OwnerTag owner={task.owner} />
          {task.due && <DueChip due={task.due} done={isDone} />}
          <SourceChip url={task.source_url} />
          {task.links?.map((l, i) => (
            <TaskLinkChip key={`${l.url}-${i}`} label={l.label} url={l.url} />
          ))}
        </div>
      )}

      {task.notes && task.notes.trim() && (
        <p
          className="mt-2 truncate text-[10px] text-muted-foreground/80"
          title={task.notes}
        >
          {task.notes}
        </p>
      )}

      <TaskActions task={task} onChanged={onChanged} />
    </div>
  )
}

// ── Sections ────────────────────────────────────────────────────────────────

function SectionHeader({
  label,
  count,
  dotClass,
  accent,
}: {
  label: string
  count: number
  dotClass?: string
  accent?: boolean
}): JSX.Element {
  return (
    <div
      className={`mb-2 flex items-center gap-2 border-b pb-1.5 ${
        accent ? 'border-amber-500/30' : 'border-border'
      }`}
    >
      {dotClass && <span className={`h-1.5 w-1.5 rounded-full ${dotClass}`} />}
      <span
        className={`text-[11px] font-bold uppercase tracking-[0.06em] ${
          accent ? 'text-amber-300' : 'text-foreground'
        }`}
      >
        {label}
      </span>
      <span className="ml-auto text-[11px] text-muted-foreground">{count}</span>
    </div>
  )
}

function CardGrid({
  tasks,
  onChanged,
}: {
  tasks: AgentTaskOut[]
  onChanged?: () => void
}): JSX.Element {
  return (
    <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
      {tasks.map((t) => (
        <TaskCard key={t.id} task={t} onChanged={onChanged} />
      ))}
    </div>
  )
}

// Subtle "N queued for Echo" indicator — accept/dispatch commands Echo will
// drain on its next turn.
function QueuedForEcho({ count }: { count: number }): JSX.Element | null {
  if (count <= 0) return null
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded border border-primary/30 bg-primary/10 px-2 py-0.5 text-[11px] font-medium text-primary"
      title="Commands queued for Echo to act on next turn"
    >
      <span className="h-1.5 w-1.5 rounded-full bg-primary" />
      {count} queued for Echo
    </span>
  )
}

function byPosition(a: AgentTaskOut, b: AgentTaskOut): number {
  return a.position - b.position
}

export function TasksBoard({
  tasks,
  onChanged,
  pendingCount = 0,
}: {
  tasks: AgentTaskOut[]
  onChanged?: () => void
  pendingCount?: number
}): JSX.Element {
  const suggested = tasks.filter((t) => t.status === 'suggested').sort(byPosition)
  const inProgress = tasks.filter((t) => t.status === 'in_progress')
  const waitingHuman = inProgress.filter((t) => !isEcho(t.assigned)).sort(byPosition)
  const echoWorking = inProgress.filter((t) => isEcho(t.assigned)).sort(byPosition)
  const done = tasks.filter((t) => t.status === 'done').sort(byPosition)
  const declined = tasks.filter((t) => t.status === 'declined').sort(byPosition)

  if (tasks.length === 0) {
    return (
      <p className="text-[13px] text-muted-foreground">No tasks yet — nothing on the board.</p>
    )
  }

  return (
    <div className="space-y-7">
      {pendingCount > 0 && (
        <div className="flex justify-end">
          <QueuedForEcho count={pendingCount} />
        </div>
      )}

      {suggested.length > 0 && (
        <section>
          <SectionHeader
            label="Suggested"
            count={suggested.length}
            dotClass="bg-muted-foreground"
          />
          <CardGrid tasks={suggested} onChanged={onChanged} />
        </section>
      )}

      {waitingHuman.length > 0 && (
        <section className="rounded-xl border border-amber-500/25 bg-amber-500/5 p-3">
          <SectionHeader label="Waiting on a human" count={waitingHuman.length} accent />
          <CardGrid tasks={waitingHuman} onChanged={onChanged} />
        </section>
      )}

      {echoWorking.length > 0 && (
        <section>
          <SectionHeader
            label="Echo working"
            count={echoWorking.length}
            dotClass="bg-primary"
          />
          <CardGrid tasks={echoWorking} onChanged={onChanged} />
        </section>
      )}

      {done.length > 0 && (
        <section>
          <SectionHeader label="Done" count={done.length} dotClass="bg-primary/40" />
          <CardGrid tasks={done} onChanged={onChanged} />
        </section>
      )}

      {declined.length > 0 && (
        <section className="opacity-60">
          <SectionHeader label="Declined" count={declined.length} />
          <div className="grid grid-cols-1 gap-1.5 sm:grid-cols-2">
            {declined.map((t) => (
              <div
                key={t.id}
                className="rounded-md border border-border bg-card/50 px-3 py-1.5 text-[11px] text-muted-foreground"
                title={t.notes || undefined}
              >
                <span className="line-through decoration-muted-foreground/40">
                  {headline(t)}
                </span>
                {t.owner && <span className="ml-1.5 text-muted-foreground/70">· {t.owner}</span>}
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  )
}
