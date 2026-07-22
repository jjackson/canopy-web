import { useEffect, useMemo, useState, type JSX } from 'react'
import { listRunners, type RunnerOut } from '@/api/harness'
import { updateAgentRunnerPreference } from '@/api/agents'

// The runner-order surface: which runner KINDS this agent prefers, in priority
// order, and which are online right now. The preferred kind claims a turn first;
// a lower kind falls back only after a short grace (server-side head-start), so an
// online cloud runner won't lose the agent's turns to the laptop and vice-versa.
// A kind not in the list never runs this agent.

const KINDS = [
  { key: 'cloud', label: 'Cloud runner' },
  { key: 'emdash', label: 'Laptop (emdash)' },
  { key: 'remote', label: 'Remote' },
] as const

function onlineByKind(runners: RunnerOut[]): Record<string, number> {
  const counts: Record<string, number> = {}
  for (const r of runners) {
    if (r.status === 'online') counts[r.kind] = (counts[r.kind] ?? 0) + 1
  }
  return counts
}

export function RunnerOrder({
  slug,
  name,
  preference,
}: {
  slug: string
  name: string
  preference: readonly string[]
}): JSX.Element {
  const [order, setOrder] = useState<string[]>([...preference])
  const [runners, setRunners] = useState<RunnerOut[]>([])
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    listRunners()
      .then(setRunners)
      .catch(() => setRunners([]))
  }, [])

  const online = useMemo(() => onlineByKind(runners), [runners])
  const dirty = useMemo(
    () => JSON.stringify(order) !== JSON.stringify([...preference]),
    [order, preference],
  )
  const unused = KINDS.filter((k) => !order.includes(k.key))
  const label = (key: string) => KINDS.find((k) => k.key === key)?.label ?? key

  const move = (i: number, d: -1 | 1) => {
    const j = i + d
    if (j < 0 || j >= order.length) return
    const next = [...order]
    ;[next[i], next[j]] = [next[j], next[i]]
    setOrder(next)
    setSaved(false)
  }
  const remove = (key: string) => {
    setOrder(order.filter((k) => k !== key))
    setSaved(false)
  }
  const add = (key: string) => {
    setOrder([...order, key])
    setSaved(false)
  }

  const save = async () => {
    setSaving(true)
    setError(null)
    try {
      await updateAgentRunnerPreference(slug, order)
      setSaved(true)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to save')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="mb-6 rounded-lg border border-border bg-card p-3" data-testid="runner-order">
      <div className="flex items-center justify-between">
        <span className="text-[11px] font-bold uppercase tracking-[0.06em] text-primary">Runner order</span>
        <button
          type="button"
          disabled={!dirty || saving}
          onClick={() => void save()}
          className="rounded-md bg-primary px-3 py-1 text-[12px] font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-40"
        >
          {saving ? 'Saving…' : 'Save order'}
        </button>
      </div>
      <p className="mt-1 text-[11px] text-muted-foreground">
        Priority order of runner kinds for {name}&apos;s turns. The top available kind claims first; a
        lower kind falls back only if the preferred one is absent. An empty list = any runner, first
        to poll.
      </p>

      <ol className="mt-3 flex flex-col gap-1.5" data-testid="runner-order-list">
        {order.length === 0 && (
          <li className="text-[12px] italic text-foreground-subtle">No preference — any eligible runner.</li>
        )}
        {order.map((key, i) => {
          const n = online[key] ?? 0
          return (
            <li
              key={key}
              className="flex items-center gap-2 rounded-md border border-border bg-background px-2 py-1.5"
            >
              <span className="w-4 text-center text-[12px] font-semibold text-muted-foreground">{i + 1}</span>
              <span
                className={`h-2 w-2 shrink-0 rounded-full ${n > 0 ? 'bg-success' : 'bg-muted-foreground/40'}`}
                title={n > 0 ? `${n} online` : 'none online'}
              />
              <span className="flex-1 text-[13px] text-foreground">{label(key)}</span>
              <span className="text-[11px] text-muted-foreground">{n > 0 ? `${n} online` : 'offline'}</span>
              <button
                type="button"
                onClick={() => move(i, -1)}
                disabled={i === 0}
                className="px-1 text-foreground-secondary hover:text-foreground disabled:opacity-30"
                aria-label="Move up"
              >
                ↑
              </button>
              <button
                type="button"
                onClick={() => move(i, 1)}
                disabled={i === order.length - 1}
                className="px-1 text-foreground-secondary hover:text-foreground disabled:opacity-30"
                aria-label="Move down"
              >
                ↓
              </button>
              <button
                type="button"
                onClick={() => remove(key)}
                className="px-1 text-muted-foreground hover:text-destructive"
                aria-label="Remove"
              >
                ×
              </button>
            </li>
          )
        })}
      </ol>

      {unused.length > 0 && (
        <div className="mt-2 flex flex-wrap items-center gap-1.5">
          <span className="text-[11px] text-muted-foreground">Add:</span>
          {unused.map((k) => (
            <button
              key={k.key}
              type="button"
              onClick={() => add(k.key)}
              className="rounded-full border border-input bg-input px-2 py-0.5 text-[11px] text-foreground-secondary hover:border-primary hover:text-primary"
            >
              + {k.label}
              {(online[k.key] ?? 0) > 0 && <span className="ml-1 text-success">•</span>}
            </button>
          ))}
        </div>
      )}

      {error && <p className="mt-1 text-[11px] text-destructive">{error}</p>}
      {saved && !error && <p className="mt-1 text-[11px] text-success">Saved.</p>}
    </div>
  )
}
