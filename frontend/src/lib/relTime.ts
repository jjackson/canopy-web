// Relative "last active" time for a session, from an ISO timestamp.
// emdash's task.status is always "in_progress" (never updated), so last_interacted_at
// is the real signal for "what ran recently / when it last finished".
export function relTime(iso: string | null | undefined, now: number = Date.now()): string {
  if (!iso) return ''
  const then = new Date(iso).getTime()
  if (Number.isNaN(then)) return ''
  const s = Math.max(0, (now - then) / 1000)
  if (s < 60) return 'just now'
  const m = Math.floor(s / 60)
  if (m < 60) return `${m}m ago`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}h ago`
  const d = Math.floor(h / 24)
  return `${d}d ago`
}

// Approximate "running now" signal: emdash bumps last_interacted_at as a session works,
// so a very recent timestamp means it's actively going (or just finished). Not a hard
// live flag — the honest label is "active", with relTime saying how recently.
export function isRecentlyActive(
  iso: string | null | undefined,
  now: number = Date.now(),
  withinSeconds: number = 120,
): boolean {
  if (!iso) return false
  const then = new Date(iso).getTime()
  if (Number.isNaN(then)) return false
  return (now - then) / 1000 < withinSeconds
}

// The transcript was written in the last ~RUNNING_WINDOW_S seconds, i.e. the agent is
// (very likely) generating output RIGHT NOW. The window is deliberately wider than the
// pipeline lag (runner reports every ~10s + the phone polls every ~10s) so an actively
// working session doesn't flicker off between updates. Caveat: a session mid-way through
// one long tool call writes nothing for a while, so it can briefly read as not-running —
// this tracks message activity, not raw CPU.
export const RUNNING_WINDOW_S = 45
export function isRunning(iso: string | null | undefined, now: number = Date.now()): boolean {
  return isRecentlyActive(iso, now, RUNNING_WINDOW_S)
}
