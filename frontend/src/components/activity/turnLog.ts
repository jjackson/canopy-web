import type { components } from "@/api/generated";

export type Turn = components["schemas"]["TurnOut"];

export type TurnFilters = {
  agent: string | null;
  origin: string | null;
  status: string | null;
};

/** Agent turns show their slug; project turns have no agent, so show the repo. */
export function agentLabel(turn: Turn): string {
  return turn.agent_slug ?? `project:${turn.project}`;
}

/** The Trigger column: what caused this turn.
 * - cron   → "cron · <fired slot>" (the slot lives in origin_ref.slot)
 * - manual → "manual · <who enqueued it>"
 * - email/api (or anything else) → the bare origin string */
export function originLabel(turn: Turn): string {
  if (turn.origin === "cron") {
    const slot = turn.origin_ref?.slot;
    return typeof slot === "string" ? `cron · ${slot}` : "cron";
  }
  if (turn.origin === "manual" && turn.enqueued_by_email) {
    return `manual · ${turn.enqueued_by_email}`;
  }
  return turn.origin;
}

/** AND across the set filters; a null filter matches everything. The agent
 * filter compares against agentLabel so project turns filter by project:<name>
 * — the same string the filter dropdown offers. */
export function matchesTurnFilters(turn: Turn, filters: TurnFilters): boolean {
  if (filters.agent && agentLabel(turn) !== filters.agent) return false;
  if (filters.origin && turn.origin !== filters.origin) return false;
  if (filters.status && turn.status !== filters.status) return false;
  return true;
}

/** Compact relative age. `now` is injected so the function is pure/testable. */
export function relativeTime(iso: string, now: Date): string {
  const secs = Math.floor((now.getTime() - new Date(iso).getTime()) / 1000);
  if (secs < 60) return "just now";
  const mins = Math.floor(secs / 60);
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

/** Status → tinted-badge className, built only from semantic tokens. Unknown
 * statuses fall back to the muted style. */
export const STATUS_TOKEN: Record<string, string> = {
  done: "bg-success/10 text-success border-success/30",
  failed: "bg-destructive/10 text-destructive border-destructive/30",
  missed: "bg-warning/10 text-warning border-warning/30",
  running: "bg-info/10 text-info border-info/30",
  claimed: "bg-muted text-muted-foreground border-border",
  queued: "bg-muted text-muted-foreground border-border",
};

export function statusToken(status: string): string {
  return STATUS_TOKEN[status] ?? "bg-muted text-muted-foreground border-border";
}
