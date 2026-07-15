import type { JSX } from 'react'
import { Link } from 'react-router-dom'
import type { AgentOut } from '@/api/agents'

// One agent's KPIs — the React counterpart of menubar.py's _card (menubar.py:385).
//
// The fleet legitimately spans workspaces (e.g. a chief-of-staff agent lives in a
// different tenant than the product agents), so the correct deep link is
// /w/<agent's workspace>/agents/<slug>. Linking to the ACTIVE workspace 404s any
// agent living elsewhere (the bug fixed once already in menubar.py, commit
// 483c821). AgentOut now serializes `workspace` (the slug), so we can build the
// tenant-scoped link directly; only a pre-tenancy agent (workspace null) falls
// back to the flat /agents/<slug> route.
export function AgentKpiCard({ agent, waiting }: { agent: AgentOut; waiting: number }): JSX.Element {
  const href = agent.workspace ? `/w/${agent.workspace}/agents/${agent.slug}` : `/agents/${agent.slug}`
  return (
    <Link
      to={href}
      data-testid={`agent-card-${agent.slug}`}
      className="flex items-center gap-3 rounded-lg border border-border bg-card p-3 transition-colors hover:border-primary/40"
    >
      <div className="min-w-0 flex-1">
        <p className="truncate text-[13px] font-semibold text-foreground">{agent.name}</p>
        <p className="mt-0.5 text-[11px] text-muted-foreground">
          {waiting > 0 ? `${waiting} waiting on you` : 'nothing waiting'}
        </p>
      </div>
      {waiting > 0 && (
        <span className="shrink-0 rounded border border-primary/30 bg-primary/10 px-1.5 py-0.5 text-[11px] font-medium text-primary">
          {waiting}
        </span>
      )}
    </Link>
  )
}
