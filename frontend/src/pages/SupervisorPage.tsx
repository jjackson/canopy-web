import { useEffect, useState, type JSX } from 'react'
import { listAgents, getFleetNeedsYou, type AgentOut, type FleetNeedsYouOut } from '@/api/agents'
import { listRunners, type RunnerOut } from '@/api/harness'
import { RunnerStatus } from '@/components/supervisor/RunnerStatus'
import { AgentKpiCard } from '@/components/supervisor/AgentKpiCard'
import { WaitingOnYou } from '@/components/supervisor/WaitingOnYou'
import { Skeleton } from 'canopy-ui'

// The ONE supervisor surface (spec 2026-07-14). Three consumers will load this
// same route: the phone as an installed PWA, the menubar's WKWebView (Phase 5),
// and a desktop browser. Phone-first layout — a single column that widens.
export default function SupervisorPage(): JSX.Element {
  const [agents, setAgents] = useState<AgentOut[] | null>(null)
  const [runners, setRunners] = useState<RunnerOut[] | null>(null)
  const [fleet, setFleet] = useState<FleetNeedsYouOut | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    Promise.all([listAgents({ limit: 100 }), listRunners(), getFleetNeedsYou()])
      .then(([page, rs, f]) => {
        if (cancelled) return
        setAgents(page.items)
        setRunners(rs)
        setFleet(f)
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(e instanceof Error ? e.message : 'Failed to load')
      })
    return () => {
      cancelled = true
    }
  }, [])

  if (error) {
    return (
      <div className="mx-auto max-w-2xl p-4">
        <p className="rounded-lg border border-destructive/30 bg-destructive/10 p-3 text-[13px] text-destructive">
          {error}
        </p>
      </div>
    )
  }

  const loading = agents === null || runners === null || fleet === null

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-5 p-4" data-testid="supervisor-page">
      <header>
        <h1 className="text-lg font-semibold text-foreground">Supervisor</h1>
        <p className="mt-0.5 text-[12px] text-muted-foreground">Your fleet, and what it needs from you.</p>
      </header>

      <section>
        <h2 className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
          Waiting on you {fleet && fleet.total_waiting > 0 ? `· ${fleet.total_waiting}` : ''}
        </h2>
        {loading ? <Skeleton className="h-24 w-full" /> : <WaitingOnYou fleet={fleet} />}
      </section>

      <section>
        <h2 className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Runners</h2>
        {loading ? <Skeleton className="h-12 w-full" /> : <RunnerStatus runners={runners} />}
      </section>

      <section>
        <h2 className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Agents</h2>
        {loading ? (
          <div className="flex flex-col gap-2">
            <Skeleton className="h-16 w-full" />
            <Skeleton className="h-16 w-full" />
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            {agents.map((a) => (
              <AgentKpiCard
                key={a.slug}
                agent={a}
                waiting={(fleet.agents ?? []).find((b) => b.agent_slug === a.slug)?.waiting_count ?? 0}
              />
            ))}
          </div>
        )}
      </section>
    </div>
  )
}
