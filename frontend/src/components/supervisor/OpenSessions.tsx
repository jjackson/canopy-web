import { useEffect, useState, type JSX } from 'react'
import { listOpenSessions, enqueueTurn, type EmdashSessionOut } from '@/api/harness'

// The open emdash sessions the runner reported — see them, and drop a prompt into a
// specific one. Continue dispatches a repo turn carrying the session's emdash:{task}
// thread_key; the runner resolves that to the SessionLink the report upserted and
// open_and_sends into that exact task. No new send path.

function SessionRow({ session }: { session: EmdashSessionOut }): JSX.Element {
  const [prompt, setPrompt] = useState('')
  const [busy, setBusy] = useState(false)
  const [sent, setSent] = useState<'ok' | string | null>(null)

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
        <span className="min-w-0 flex-1 truncate text-[13px] font-semibold text-foreground">
          {session.project} · {session.emdash_task}
        </span>
        <span className="shrink-0 text-[11px] text-muted-foreground">{session.status}</span>
      </div>
      <div className="mt-2 flex gap-2">
        <input
          data-testid={`session-input-${session.emdash_task}`}
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') void send() }}
          placeholder="Continue this session…"
          className="min-w-0 flex-1 rounded border border-input bg-input px-2 py-1.5 text-[13px] text-foreground placeholder:text-muted-foreground"
        />
        <button
          type="button"
          data-testid={`session-send-${session.emdash_task}`}
          onClick={() => void send()}
          disabled={busy || prompt.trim() === ''}
          className="rounded bg-primary px-3 py-1.5 text-[13px] font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
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
      .then((s) => { if (!cancelled) setSessions(s) })
      .catch((e) => {
        if (cancelled) return
        setError(e instanceof Error ? e.message : 'Failed to load sessions')
        setSessions([])
      })
    return () => { cancelled = true }
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
    return <p className="text-[12px] text-muted-foreground" data-testid="sessions-empty">No open sessions.</p>
  }
  return (
    <div className="flex flex-col gap-2" data-testid="open-sessions">
      {sessions.map((s) => <SessionRow key={s.id} session={s} />)}
    </div>
  )
}
