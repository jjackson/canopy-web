// Harness API client — the runner registry and turn lifecycle. Separate from
// ./agents because a Runner is not an agent: the harness is framework tier and
// the agent surface is product tier (see ARCHITECTURE.md).
import { apiV2 } from './client.v2'
import type { components } from './generated'

export type RunnerOut = components['schemas']['RunnerOut']
export type TurnOut = components['schemas']['TurnOut']

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

// Dispatch a command to an AGENT from the phone composer. Agent turns route
// through the flat mount cleanly — the server resolves the agent's single
// workspace, so there is no tenant ambiguity to disambiguate.
//
// Repo (project) dispatch is deliberately NOT here yet: a project turn carries
// its OWN workspace, and a repo like canopy-web is not owned by one workspace,
// so the composer must first answer "which tenant does this repo turn belong to"
// AND route to /api/w/{ws}/... (the flat route 422s a multi-workspace user).
// That is a real design decision, tracked in the Phase 3 plan — not a rushed
// raw-fetch here.
export async function enqueueTurn(input: {
  agentSlug: string
  prompt: string
}): Promise<TurnOut> {
  const { agentSlug, prompt } = input
  // A stable-enough idempotency key: a double-tap of Send within the same second
  // collapses server-side rather than firing twice.
  const key = `cmd-${agentSlug}-${Date.now()}`
  const res = await apiV2.POST('/api/harness/turns/', {
    body: {
      agent_slug: agentSlug,
      project: '',
      origin: 'manual',
      idempotency_key: key,
      prompt,
      origin_ref: {},
      routing: 'prefer_local',
    },
  })
  return unwrap(res, 'enqueueTurn')
}

// Un-queue a misfired turn (queued only; the server 409s a running turn).
export async function cancelTurn(turnId: string): Promise<TurnOut> {
  const res = await apiV2.POST('/api/harness/turns/{turn_id}/cancel', {
    params: { path: { turn_id: turnId } },
  })
  return unwrap(res, 'cancelTurn')
}
