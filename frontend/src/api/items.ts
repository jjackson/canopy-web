// Typed against the generated OpenAPI types — this file cannot drift from the
// server. Workspace scoping is handled by apiV2's middleware (see
// WS_SCOPED_API_PREFIXES in ./client.v2), not here.
import { apiV2 } from './client.v2'
import type { components } from './generated'

type Schemas = components['schemas']

export type ItemOut = Schemas['ItemOut']

/** CLOSED set — a generic inbox renders these three for any item, including one
 *  it has never seen. Only `implement` dispatches; a question is resolved by its
 *  comment instead. */
export type ItemDecision = 'implement' | 'skip' | 'defer'

// 401 never reaches here: apiV2's middleware redirects to login first.
function unwrap<T>(res: { data?: T; error?: unknown }, what: string): T {
  if (res.error !== undefined || res.data === undefined) {
    throw new Error(`${what} failed: ${JSON.stringify(res.error ?? 'no data')}`)
  }
  return res.data
}

// openapi-fetch's Readable<T> degrades `readonly Foo[]` into an ArrayLike-shaped
// object and rewrites nested object types, so a response never lands as the
// schema type by identity. See the long-form explanation on `toPage` in
// ./agents.ts — same gap, same fix: accept the structural shape and rebuild with
// Array.from / a field-wise copy, no casts.
type ReadableItem = {
  readonly id: string
  readonly agent_slug: string
  readonly idempotency_key: string
  readonly kind: string
  readonly title: string
  readonly body: string
  readonly origin: string
  readonly origin_ref: Readonly<Record<string, unknown>>
  readonly state: string
  readonly decision: string
  readonly comment: string
  readonly decided_by: string
  readonly decided_at?: string | null
  readonly dispatch: ArrayLike<Readonly<Record<string, unknown>>>
  readonly dispatched_at?: string | null
  readonly batch_key: string
  readonly created_at: string
}

function toItem(i: ReadableItem): ItemOut {
  return {
    id: i.id,
    agent_slug: i.agent_slug,
    idempotency_key: i.idempotency_key,
    kind: i.kind,
    title: i.title,
    body: i.body,
    origin: i.origin,
    origin_ref: { ...i.origin_ref },
    state: i.state,
    decision: i.decision,
    comment: i.comment,
    decided_by: i.decided_by,
    decided_at: i.decided_at ?? null,
    dispatch: Array.from(i.dispatch, (d) => ({ ...d })),
    dispatched_at: i.dispatched_at ?? null,
    batch_key: i.batch_key,
    created_at: i.created_at,
  }
}

export async function listItems(
  slug: string,
  query: { batch?: string; state?: string; kind?: string } = {},
): Promise<ItemOut[]> {
  const rows = unwrap(
    await apiV2.GET('/api/agents/{slug}/items/', { params: { path: { slug }, query } }),
    'listItems',
  )
  return Array.from(rows, toItem)
}

export async function decideItem(
  itemId: string,
  decision: ItemDecision | '',
  comment = '',
): Promise<ItemOut> {
  const row = unwrap(
    await apiV2.POST('/api/items/{item_id}/decide', {
      params: { path: { item_id: itemId } },
      body: { decision, comment },
    }),
    'decideItem',
  )
  return toItem(row)
}
