import { useEffect, useState, type JSX } from 'react'
import { listOpenSessions, enqueueTurn, type EmdashSessionOut } from '@/api/harness'
import { normalizeRecentMessages, type RecentMessage } from '@/lib/recentMessages'
import { relTime, isRecentlyActive } from '@/lib/relTime'

// The open emdash sessions the runner reported — glance at what each is doing (the
// recent-message tail), and drop a prompt into a specific one. Continue dispatches a
// repo turn carrying the session's emdash:{task} thread_key; the runner resolves that
// to the SessionLink the report upserted and open_and_sends into that exact task.

function Chevron({ open }: { open: boolean }): JSX.Element {
  return (
    <svg
      className={`mt-0.5 h-3 w-3 shrink-0 text-muted-foreground transition-transform ${open ? 'rotate-180' : ''}`}
      viewBox="0 0 12 12"
      fill="none"
      aria-hidden="true"
    >
      <path d="M3 4.5 6 7.5 9 4.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function RoleChip({ role }: { role: string }): JSX.Element {
  const isAssistant = role === 'assistant'
  return (
    <span
      className={`mt-0.5 shrink-0 rounded px-1.5 py-0.5 text-[9px] font-semibold uppercase leading-none tracking-wide ${
        isAssistant ? 'bg-primary/10 text-primary' : 'bg-muted text-muted-foreground'
      }`}
    >
      {isAssistant ? 'agent' : 'you'}
    </span>
  )
}

function MessageBubble({ msg }: { msg: RecentMessage }): JSX.Element {
  return (
    <div className="flex items-start gap-2 rounded-md bg-muted/40 p-2">
      <RoleChip role={msg.role} />
      <p className="min-w-0 flex-1 whitespace-pre-wrap break-words text-[12px] leading-snug text-foreground-secondary">
        {msg.text}
      </p>
    </div>
  )
}

function RecentActivity({ task, messages }: { task: string; messages: RecentMessage[] }): JSX.Element | null {
  const [expanded, setExpanded] = useState(false)
  if (messages.length === 0) return null
  const latest = messages[messages.length - 1]

  return (
    <div className="mt-2" data-testid={`session-tail-${task}`}>
      {!expanded ? (
        <>
          <button
            type="button"
            data-testid={`session-tail-toggle-${task}`}
            onClick={() => setExpanded(true)}
            className="flex w-full items-start gap-2 rounded-md bg-muted/40 p-2 text-left active:bg-muted"
          >
            <RoleChip role={latest.role} />
            <span className="line-clamp-2 min-w-0 flex-1 text-[12px] leading-snug text-foreground-secondary">
              {latest.text}
            </span>
            <Chevron open={false} />
          </button>
          {messages.length > 1 && (
            <p className="mt-1 pl-1 text-[10px] text-muted-foreground">
              {messages.length} recent messages · tap to expand
            </p>
          )}
        </>
      ) : (
        <div className="flex flex-col gap-1.5">
          {messages.map((m, i) => (
            <MessageBubble key={i} msg={m} />
          ))}
          <button
            type="button"
            data-testid={`session-tail-toggle-${task}`}
            onClick={() => setExpanded(false)}
            className="flex items-center gap-1 self-start py-1 text-[11px] text-muted-foreground hover:text-foreground-secondary"
          >
            <Chevron open={true} /> Collapse
          </button>
        </div>
      )}
    </div>
  )
}

function SessionRow({ session }: { session: EmdashSessionOut }): JSX.Element {
  const [prompt, setPrompt] = useState('')
  const [busy, setBusy] = useState(false)
  const [sent, setSent] = useState<'ok' | string | null>(null)
  const messages = normalizeRecentMessages(session.recent_messages)
  const active = isRecentlyActive(session.last_interacted_at)

  async function send(): Promise<void> {
    if (busy || prompt.trim() === '') return
    setBusy(true)
    setSent(null)
    try {
      await enqueueTurn({
        project: session.project,
        workspace: session.workspace,
        prompt: prompt.trim(),
        threadKey: `emdash:${session.emdash_task}`,
      })
      setSent('ok')
      setPrompt('')
    } catch (e) {
      setSent(e instanceof Error ? e.message : 'Failed to send')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="rounded-lg border border-border bg-card p-3" data-testid={`session-${session.emdash_task}`}>
      <div className="flex items-center gap-2">
        {/* Project is the group header now; the row shows just the task. */}
        <span className="min-w-0 flex-1 truncate text-[13px] font-semibold text-foreground">
          {session.emdash_task}
        </span>
        {/* Last-active time, not emdash's always-"in_progress" status. A recent
            timestamp (green dot) is the best "running now" signal available. */}
        <span
          className={`flex shrink-0 items-center gap-1 text-[11px] ${
            active ? 'text-success' : 'text-muted-foreground'
          }`}
        >
          {active && <span className="inline-block h-1.5 w-1.5 rounded-full bg-success" />}
          {relTime(session.last_interacted_at) || session.status}
        </span>
      </div>

      <RecentActivity task={session.emdash_task} messages={messages} />

      <div className="mt-2 flex gap-2">
        <input
          data-testid={`session-input-${session.emdash_task}`}
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') void send()
          }}
          placeholder="Continue this session…"
          className="min-w-0 flex-1 rounded border border-input bg-input px-2 py-2 text-[13px] text-foreground placeholder:text-muted-foreground"
        />
        <button
          type="button"
          data-testid={`session-send-${session.emdash_task}`}
          onClick={() => void send()}
          disabled={busy || prompt.trim() === ''}
          className="rounded bg-primary px-3 py-2 text-[13px] font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
        >
          {busy ? 'Sending…' : 'Continue'}
        </button>
      </div>
      {sent === 'ok' && (
        <p className="mt-1 text-[12px] text-success" data-testid={`session-sent-${session.emdash_task}`}>
          Sent to {session.emdash_task}.
        </p>
      )}
      {sent && sent !== 'ok' && <p className="mt-1 text-[12px] text-destructive">{sent}</p>}
    </div>
  )
}

export function OpenSessions(): JSX.Element {
  const [sessions, setSessions] = useState<EmdashSessionOut[] | null>(null)
  // Distinct from `sessions === []` (genuinely zero) — a flaky fetch must not
  // collapse into "No open sessions." with no error signal. Mirrors
  // SupervisorPage's per-band `errs` convention (BandError).
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    let cancelled = false
    listOpenSessions()
      .then((s) => {
        if (!cancelled) setSessions(s)
      })
      .catch((e) => {
        if (cancelled) return
        setError(e instanceof Error ? e.message : 'Failed to load sessions')
        setSessions([])
      })
    return () => {
      cancelled = true
    }
  }, [])

  if (sessions === null) return <p className="text-[12px] text-muted-foreground">Loading sessions…</p>
  if (error) {
    return (
      <p
        className="rounded-lg border border-destructive/30 bg-destructive/10 p-3 text-[13px] text-destructive"
        data-testid="sessions-error"
      >
        {error}
      </p>
    )
  }
  if (sessions.length === 0) {
    return (
      <p className="text-[12px] text-muted-foreground" data-testid="sessions-empty">
        No open sessions.
      </p>
    )
  }
  // Group by project (a header per project), projects alphabetical, sessions within
  // each group left in the server's most-recently-active order.
  const groups = new Map<string, EmdashSessionOut[]>()
  for (const s of sessions) {
    const key = s.project || '(no project)'
    const arr = groups.get(key)
    if (arr) arr.push(s)
    else groups.set(key, [s])
  }
  const ordered = [...groups.entries()].sort((a, b) => a[0].localeCompare(b[0]))

  return (
    <div className="flex flex-col gap-4" data-testid="open-sessions">
      {ordered.map(([project, rows]) => (
        <div key={project} className="flex flex-col gap-2" data-testid={`session-group-${project}`}>
          <h3 className="flex items-baseline gap-1.5 px-1 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
            {project}
            <span className="font-normal normal-case text-foreground-subtle">{rows.length}</span>
          </h3>
          {rows.map((s) => (
            <SessionRow key={s.id} session={s} />
          ))}
        </div>
      ))}
    </div>
  )
}
