import { useState, type JSX } from 'react'
import type { RunnerOut } from '@/api/harness'
import type { AgentOut } from '@/api/agents'
import { RunnerOrder } from '@/components/agents/RunnerOrder'
import { agentsForKind, ordinal } from './runnerPriority'

// A runner's full state — the click-through from the Runners tab's runner list.
// Leads with the signals that actually matter: is it AVAILABLE to fire a turn
// (online ∧ ready — a stale runner reporting last-known ready=true is NOT), what
// agents/repos it can drive, and who paired it (the owner that governs what it may
// work for). Plus which agents prioritize this runner's KIND — editable in place.
export function RunnerDetail({
  runner,
  agents,
  runners,
  onAgentSaved,
  onBack,
}: {
  runner: RunnerOut
  agents: AgentOut[]
  runners: RunnerOut[]
  onAgentSaved: (slug: string, pref: string[]) => void
  onBack: () => void
}): JSX.Element {
  const online = runner.status === 'online'
  // Real availability, not last-known ready: a stale runner's ready flag is
  // whatever it reported on its final heartbeat and no longer reflects reality.
  const available = online && runner.ready
  const badge = available
    ? { text: 'available', cls: 'bg-success/15 text-success' }
    : online
      ? { text: 'not ready', cls: 'bg-destructive/15 text-destructive' }
      : { text: runner.status || 'offline', cls: 'bg-muted text-muted-foreground' }
  const caps = (runner.capabilities ?? {}) as { agents?: string[]; projects?: string[] }
  const { ranked, acceptsAll } = agentsForKind(agents, runner.kind)
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set())
  const toggle = (slug: string) =>
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(slug)) next.delete(slug)
      else next.add(slug)
      return next
    })

  const row = (label: string, value: string) => (
    <div className="flex items-baseline justify-between gap-3 border-b border-border py-1.5">
      <span className="text-[11px] uppercase tracking-wide text-muted-foreground">{label}</span>
      <span className="min-w-0 truncate text-[13px] text-foreground">{value}</span>
    </div>
  )

  const agentRow = (a: AgentOut, badge: string) => (
    <div key={a.slug} className="rounded-md border border-border bg-background">
      <button
        type="button"
        onClick={() => toggle(a.slug)}
        className="flex w-full items-center gap-2 px-2 py-1.5 text-left"
        data-testid={`runner-priority-agent-${a.slug}`}
      >
        <span className="min-w-0 flex-1 truncate text-[13px] text-foreground">{a.name}</span>
        <span className="shrink-0 rounded bg-muted px-1.5 py-0.5 text-[11px] text-muted-foreground">{badge}</span>
        <span className="shrink-0 text-muted-foreground">{expanded.has(a.slug) ? '▾' : '▸'}</span>
      </button>
      {expanded.has(a.slug) && (
        <div className="px-2 pb-2">
          <RunnerOrder
            slug={a.slug}
            name={a.name}
            preference={a.runner_preference ?? []}
            runners={runners}
            onSaved={(pref) => onAgentSaved(a.slug, pref)}
          />
        </div>
      )}
    </div>
  )

  return (
    <div className="flex flex-col gap-2" data-testid={`runner-detail-${runner.name}`}>
      <button type="button" onClick={onBack} className="self-start text-[12px] text-primary" data-testid="runner-detail-back">
        ← Runners
      </button>
      <div className="flex items-center gap-2">
        <span className={`h-2 w-2 rounded-full ${online ? 'bg-success' : 'bg-muted-foreground'}`} />
        <span className="text-[15px] font-semibold text-foreground">{runner.name}</span>
        <span
          data-testid="runner-detail-ready"
          className={`ml-auto rounded px-1.5 py-0.5 text-[11px] ${badge.cls}`}
        >
          {badge.text}
        </span>
      </div>
      {online && !runner.ready && runner.ready_note && (
        <p className="text-[12px] text-destructive" data-testid="runner-detail-why">{runner.ready_note}</p>
      )}
      <div className="rounded-lg border border-border bg-card p-3">
        {row('agents', (caps.agents ?? []).join(', ') || '—')}
        {row('projects', (caps.projects ?? []).join(', ') || '—')}
        {row('kind', runner.kind ?? '')}
        {row('paired by', runner.paired_by_email ?? '—')}
        {/* host only matters for emdash (per-macOS-account session reuse); cloud
            runners report no host, so skip the empty row entirely. */}
        {runner.host && row('host', runner.host)}
        {row('status', runner.status ?? 'unknown')}
      </div>

      {/* Which agents route work to this runner's KIND, and how strongly. */}
      <div className="flex flex-col gap-1.5" data-testid="runner-priority">
        <span className="text-[11px] uppercase tracking-wide text-muted-foreground">
          Agent priority · {runner.kind || 'unknown'}
        </span>
        {ranked.length === 0 && acceptsAll.length === 0 && (
          <p className="text-[12px] text-muted-foreground">No agents prioritize this runner kind.</p>
        )}
        {ranked.map((r) => agentRow(r.agent, ordinal(r.rank)))}
        {acceptsAll.length > 0 && (
          <>
            <span className="mt-1 text-[11px] text-foreground-subtle">any — accepts all kinds</span>
            {acceptsAll.map((a) => agentRow(a, 'any'))}
          </>
        )}
      </div>
    </div>
  )
}
