// Harness API client — the runner registry and turn lifecycle. Separate from
// ./agents because a Runner is not an agent: the harness is framework tier and
// the agent surface is product tier (see ARCHITECTURE.md).
import { apiV2 } from './client.v2'
import type { components } from './generated'

export type RunnerOut = components['schemas']['RunnerOut']

function unwrap<T>(res: { data?: T; error?: unknown }, what: string): T {
  if (res.error !== undefined || res.data === undefined) {
    throw new Error(`${what} failed: ${JSON.stringify(res.error ?? 'no data')}`)
  }
  return res.data
}

export async function listRunners(): Promise<RunnerOut[]> {
  const res = await apiV2.GET('/api/harness/runners/')
  // openapi-fetch's Readable<T> helper degrades `readonly Foo[]` into an
  // ArrayLike-shaped object (numeric index + length, no Symbol.iterator) — see
  // ./agents.ts's toPage comment for the full explanation. Array.from rebuilds
  // a real array rather than casting.
  return Array.from(unwrap(res, 'listRunners'))
}
