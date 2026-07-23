import { useEffect, useRef, useState, type JSX } from 'react'
import { listOpenSessions, enqueueTurn, getTurn, type EmdashSessionOut } from '@/api/harness'
import { normalizeRecentMessages, type RecentMessage } from '@/lib/recentMessages'
import { relTime, isRunning } from '@/lib/relTime'

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
  // idle -> sending (queued, waiting for the runner) -> delivered (running in the
  // session) | error. "delivered" is the honest confirmation: it lands only when the
  // turn actually starts executing, not on enqueue (the old green fired too early).
  const [phase, setPhase] = useState<'idle' | 'sending' | 'delivered' | 'error'>('idle')
  const [errMsg, setErrMsg] = useState('')
  const [deliveredRunner, setDeliveredRunner] = useState('')
  const messages = normalizeRecentMessages(session.recent_messages)
  const running = isRunning(session.last_interacted_at)
  const mounted = useRef(true)
  useEffect(() => () => { mounted.current = false }, [])

  async function send(): Promise<void> {
    if (busy || prompt.trim() === '') return
    setBusy(true)
    setPhase('sending')
    setErrMsg('')
    let turnId: string
    try {
      const turn = await enqueueTurn({
        project: session.project,
        workspace: session.workspace,
        prompt: prompt.trim(),
        threadKey: `emdash:${session.emdash_task}`,
      })
      turnId = turn.id
      setPrompt('')
    } catch (e) {
      if (!mounted.current) return
      setPhase('error')
      setErrMsg(e instanceof Error ? e.message : 'Failed to send')
      setBusy(false)
      return
    }
    // Poll the turn until the runner claims it and starts executing (running = the
    // prompt has been delivered into the live session), or it finishes/fails. Give
    // up after ~90s (runner offline) but keep the queued note so it's not lost.
    const deadline = Date.now() + 90_000
    const tick = async (): Promise<void> => {
      if (!mounted.current) return
      let status = ''
      let note = ''
      let runner = ''
      try {
        const t = await getTurn(turnId)
        status = t.status
        note = t.result_note
        runner = t.claimed_by_name ?? ''
      } catch {
        // transient error — fall through to retry
      }
      if (!mounted.current) return
      if (status === 'running' || status === 'done' || status === 'needs_human') {
        setDeliveredRunner(runner || session.runner_name)
        setPhase('delivered')
        setBusy(false)
        return
      }
      if (status === 'failed') {
        setPhase('error')
        setErrMsg(note || 'The session run failed.')
        setBusy(false)
        return
      }
      if (Date.now() < deadline) window.setTimeout(() => void tick(), 1500)
      else setBusy(false) // still queued after 90s — stop the spinner, keep the note
    }
    window.setTimeout(() => void tick(), 1200)
  }

  return (
    <div className="rounded-lg border border-border bg-card p-3" data-testid={`session-${session.emdash_task}`}>
      <div className="flex items-center gap-2">
        {/* Project is the group header now; the row shows just the task. */}
        <span className="min-w-0 flex-1 truncate text-[13px] font-semibold text-foreground">
          {session.emdash_task}
        </span>
        {/* "running" (pulsing) when the transcript was just written — the agent is
            working now; otherwise the last-active age. Never emdash's fake status. */}
        {running ? (
          <span className="flex shrink-0 items-center gap-1 text-[11px] font-medium text-success">
            <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-success" />
            running
          </span>
        ) : (
          <span className="shrink-0 text-[11px] text-muted-foreground">
            {relTime(session.last_interacted_at) || session.status}
          </span>
        )}
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
          {busy ? 'Sending…' : 'Send'}
        </button>
      </div>
      {phase === 'sending' && (
        <p
          className="mt-1 flex items-center gap-1.5 text-[12px] text-muted-foreground"
          data-testid={`session-sending-${session.emdash_task}`}
        >
          <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-muted-foreground" />
          Sending to {session.emdash_task}… waiting for the runner
        </p>
      )}
      {phase === 'delivered' && (
        <p className="mt-1 text-[12px] text-success" data-testid={`session-sent-${session.emdash_task}`}>
          ✓ Delivered — running on {deliveredRunner || session.runner_name}.
        </p>
      )}
      {phase === 'error' && <p className="mt-1 text-[12px] text-destructive">{errMsg}</p>}
    </div>
  )
}

export function OpenSessions(
  { liveSessions }: { liveSessions?: EmdashSessionOut[] | null } = {},
): JSX.Element {
  const [sessions, setSessions] = useState<EmdashSessionOut[] | null>(null)
  // Distinct from `sessions === []` (genuinely zero) — a flaky fetch must not
  // collapse into "No open sessions." with no error signal. Mirrors
  // SupervisorPage's per-band `errs` convention (BandError).
  const [error, setError] = useState<string | null>(null)
  const hasData = useRef(false)
  useEffect(() => {
    let cancelled = false
    const load = (): void => {
      listOpenSessions()
        .then((s) => {
          if (cancelled) return
          hasData.current = true
          setSessions(s)
          setError(null)
        })
        .catch((e) => {
          // Keep the last-good list on a transient refresh error; only surface an
          // error if we never loaded anything.
          if (cancelled || hasData.current) return
          setError(e instanceof Error ? e.message : 'Failed to load sessions')
          setSessions([])
        })
    }
    load()
    // The live path is now the WebSocket push (liveSessions): the runner re-reports
    // the instant a session's transcript grows, and the server fans it to every
    // connected device at once — so this poll is just a slow fallback for when the
    // socket is down. The initial load above gives immediate data before the first push.
    const id = window.setInterval(load, 20_000)
    return () => {
      cancelled = true
      window.clearInterval(id)
    }
  }, [])

  // Prefer the live WebSocket push once it has arrived; fall back to the fetched list.
  const displaySessions = liveSessions ?? sessions

  if (displaySessions === null) return <p className="text-[12px] text-muted-foreground">Loading sessions…</p>
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
  if (displaySessions.length === 0) {
    return (
      <p className="text-[12px] text-muted-foreground" data-testid="sessions-empty">
        No open sessions.
      </p>
    )
  }
  // Group by project (a header per project), projects alphabetical, sessions within
  // each group left in the server's most-recently-active order.
  const groups = new Map<string, EmdashSessionOut[]>()
  for (const s of displaySessions) {
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
          {/* Key by task, NOT s.id: the report re-mints EmdashSession ids every tick,
              so keying by id would remount every row on each poll and wipe in-progress
              typing / Sending state. Task is stable within a project. */}
          {rows.map((s) => (
            <SessionRow key={s.emdash_task} session={s} />
          ))}
        </div>
      ))}
    </div>
  )
}
