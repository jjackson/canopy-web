import type { JSX } from 'react'
import type { RunnerOut } from '@/api/harness'

// A runner's full state — the click-through from the Agents tab's runner list.
// Surfaces the two signals that matter: is it ON (heartbeating) and is it READY
// (can actually fire a turn), with the reason it isn't.
export function RunnerDetail({ runner, onBack }: { runner: RunnerOut; onBack: () => void }): JSX.Element {
  const online = runner.status === 'online'
  const caps = (runner.capabilities ?? {}) as { agents?: string[]; projects?: string[] }
  const row = (label: string, value: string) => (
    <div className="flex items-baseline justify-between gap-3 border-b border-border py-1.5">
      <span className="text-[11px] uppercase tracking-wide text-muted-foreground">{label}</span>
      <span className="min-w-0 truncate text-[13px] text-foreground">{value}</span>
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
          className={`ml-auto rounded px-1.5 py-0.5 text-[11px] ${runner.ready ? 'bg-success/15 text-success' : 'bg-destructive/15 text-destructive'}`}
        >
          {runner.ready ? 'ready' : 'not ready'}
        </span>
      </div>
      {!runner.ready && runner.ready_note && (
        <p className="text-[12px] text-destructive" data-testid="runner-detail-why">{runner.ready_note}</p>
      )}
      <div className="rounded-lg border border-border bg-card p-3">
        {row('status', online ? 'online' : (runner.status ?? 'unknown'))}
        {row('kind', runner.kind ?? '')}
        {row('host', runner.host ?? '')}
        {row('workspace', runner.workspace ?? '')}
        {row('agents', (caps.agents ?? []).join(', ') || '—')}
        {row('projects', (caps.projects ?? []).join(', ') || '—')}
      </div>
    </div>
  )
}
