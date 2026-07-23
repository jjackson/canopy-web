import type { Message } from "./protocol";

/**
 * Merge an older page (from the REST scroll-back endpoint) into the current
 * transcript: prepend, dedupe by turn_index, keep chronological. Pure — no React,
 * no WebSocket — so the container can apply "Load earlier" to the socket's
 * SessionState without a new WS frame. Returns `current` unchanged (same
 * reference) when nothing new prepends, so callers can skip a re-render.
 */
export function prependHistory(current: Message[], older: Message[]): Message[] {
  if (older.length === 0) return current;
  const seen = new Set(current.map((m) => m.turn_index));
  const fresh = older.filter((m) => !seen.has(m.turn_index));
  if (fresh.length === 0) return current;
  return [...fresh, ...current].sort((a, b) => a.turn_index - b.turn_index);
}
