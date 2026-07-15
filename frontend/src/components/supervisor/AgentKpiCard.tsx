import type { JSX } from 'react'
import { Link } from 'react-router-dom'
import type { AgentOut } from '@/api/agents'

// One agent's KPIs — the React counterpart of menubar.py's _card (menubar.py:385).
//
// NOTE: AgentOut does not expose the agent's workspace slug — apps/agents/schemas.py
// only accepts `workspace` as write-only input on AgentIn (to home/move an agent);
// AgentOut/AgentDetailOut never serialize it back out. So this card cannot link
// straight into the agent's own workspace and falls back to the flat /agents/<slug>
// path, which resolves the ACTIVE workspace — the exact 404 that hid Ada and Eva
// (commit 483c821) for anyone whose active workspace isn't the agent's home. Fixing
// this for real needs AgentOut to grow a `workspace` (slug) field server-side; that
// is out of scope here per this task's brief (no backend field additions).
export function AgentKpiCard({ agent, waiting }: { agent: AgentOut; waiting: number }): JSX.Element {
  const href = `/agents/${agent.slug}`
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
