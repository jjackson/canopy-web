import { useEffect, useState, type JSX } from 'react'
import { listAgents, getFleetNeedsYou, type AgentOut, type FleetNeedsYouOut } from '@/api/agents'
import { listRunners, type RunnerOut } from '@/api/harness'
import { RunnerStatus } from '@/components/supervisor/RunnerStatus'
import { AgentKpiCard } from '@/components/supervisor/AgentKpiCard'
import { WaitingOnYou } from '@/components/supervisor/WaitingOnYou'
import { InstallPrompt } from '@/pwa/InstallPrompt'
import { PushToggle } from '@/pwa/PushToggle'
import { setBadge } from '@/pwa/usePush'
import { Skeleton } from 'canopy-ui'

function BandError({ message }: { message: string }): JSX.Element {
  return (
    <p className="rounded-lg border border-destructive/30 bg-destructive/10 p-3 text-[13px] text-destructive">
      {message}
    </p>
  )
}

// The ONE supervisor surface (spec 2026-07-14). Three consumers will load this
// same route: the phone as an installed PWA, the menubar's WKWebView (Phase 5),
// and a desktop browser. Phone-first layout — a single column that widens.
export default function SupervisorPage(): JSX.Element {
  const [agents, setAgents] = useState<AgentOut[] | null>(null)
  const [runners, setRunners] = useState<RunnerOut[] | null>(null)
  const [fleet, setFleet] = useState<FleetNeedsYouOut | null>(null)
  // Per-band errors, not one page-level error: on cellular a single flaky call
  // is the common case, and Promise.all would blank all three bands for it.
  const [errs, setErrs] = useState<{ agents?: string; runners?: string; fleet?: string }>({})

  useEffect(() => {
    let cancelled = false
    const msg = (r: PromiseRejectedResult) =>
      r.reason instanceof Error ? r.reason.message : 'Failed to load'

    Promise.allSettled([listAgents({ limit: 100 }), listRunners(), getFleetNeedsYou()]).then(
      ([a, r, f]) => {
        if (cancelled) return
        if (a.status === 'fulfilled') setAgents(a.value.items)
        else setErrs((e) => ({ ...e, agents: msg(a) }))
        if (r.status === 'fulfilled') setRunners(r.value)
        else setErrs((e) => ({ ...e, runners: msg(r) }))
        if (f.status === 'fulfilled') setFleet(f.value)
        else setErrs((e) => ({ ...e, fleet: msg(f) }))
      },
    )
    return () => {
      cancelled = true
    }
  }, [])

  // The app-icon count. Android honours this; elsewhere it no-ops.
  useEffect(() => {
    if (fleet) setBadge(fleet.total_waiting)
  }, [fleet])

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-5 p-4" data-testid="supervisor-page">
      <header>
        <h1 className="text-lg font-semibold text-foreground">Supervisor</h1>
        <p className="mt-0.5 text-[12px] text-muted-foreground">Your fleet, and what it needs from you.</p>
      </header>

      <InstallPrompt />
      <PushToggle />

      <section>
        <h2 className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
          Waiting on you {fleet && fleet.total_waiting > 0 ? `· ${fleet.total_waiting}` : ''}
        </h2>
        {errs.fleet ? (
          <BandError message={errs.fleet} />
        ) : fleet === null ? (
          <Skeleton className="h-24 w-full" />
        ) : (
          <WaitingOnYou fleet={fleet} />
        )}
      </section>

      <section>
        <h2 className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Runners</h2>
        {errs.runners ? (
          <BandError message={errs.runners} />
        ) : runners === null ? (
          <Skeleton className="h-12 w-full" />
        ) : (
          <RunnerStatus runners={runners} />
        )}
      </section>

      <section>
        <h2 className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Agents</h2>
        {errs.agents ? (
          <BandError message={errs.agents} />
        ) : agents === null ? (
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
                waiting={fleet ? ((fleet.agents ?? []).find((b) => b.agent_slug === a.slug)?.waiting_count ?? 0) : 0}
              />
            ))}
          </div>
        )}
      </section>
    </div>
  )
}
