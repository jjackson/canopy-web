export type RecentMessage = { role: string; text: string }

// The server serializes recent_messages as an untyped list (unknown[] in the
// generated OpenAPI types). Coerce defensively so a malformed tail can never
// crash the render: keep only entries with a non-empty text, defaulting a
// missing/blank role to "assistant".
export function normalizeRecentMessages(raw: readonly unknown[]): RecentMessage[] {
  const out: RecentMessage[] = []
  for (const item of raw) {
    if (item && typeof item === 'object') {
      const rec = item as Record<string, unknown>
      const role = typeof rec.role === 'string' ? rec.role : ''
      const text = typeof rec.text === 'string' ? rec.text : ''
      if (text) out.push({ role: role || 'assistant', text })
    }
  }
  return out
}
