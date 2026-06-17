// Agent Workspace API client.
//
// The /api/agents/* routes are live on the backend but are not yet present in
// the generated OpenAPI types (frontend/src/api/generated.ts), so this client
// can't ride the typed `apiV2` openapi-fetch client like shareouts/walkthroughs
// do. Instead it uses a thin same-origin fetch that mirrors apiV2's auth
// behavior (credentials: 'same-origin' + redirect-to-login on 401) and the
// response shapes are declared locally below. When the types are regenerated
// (`npm run gen:api`), this file can be migrated to `apiV2.GET(...)` without
// touching callers.

export interface Page<T> {
  items: T[]
  total: number
  offset: number
  limit: number
}

export interface AgentOut {
  id: number
  slug: string
  name: string
  description: string
  persona: string
  email: string
  avatar_url: string
  created_at: string
  updated_at: string
}

export interface AgentDetailOut extends AgentOut {
  sync_count: number
  work_product_count: number
  skill_count: number
  latest_sync_at: string | null
}

export interface AgentSyncOut {
  id: number
  agent_slug: string
  period_start: string
  period_end: string
  title: string
  summary: string
  doc_url: string
  self_grades: Record<string, string>
  source: string
  created_at: string
}

export interface AgentWorkProductOut {
  id: number
  agent_slug: string
  title: string
  kind: string
  url: string
  description: string
  tags: string[]
  source: string
  created_at: string
}

export interface AgentSkillOut {
  id: number
  agent_slug: string
  name: string
  description: string
  url: string
  improvement_note: string
  updated_at: string
}

// Mirrors client.v2's auth: anonymous 401s on a non-public route bounce to the
// Google login flow; everything else surfaces as a thrown Error.
function redirectToLogin(): never {
  const next = encodeURIComponent(window.location.pathname + window.location.search)
  window.location.href = `/accounts/google/login/?next=${next}`
  throw new Error('Redirecting to login')
}

function isPublicLinkRoute(): boolean {
  const p = window.location.pathname
  return p.startsWith('/review/') || p.startsWith('/share/')
}

async function getJson<T>(path: string, what: string): Promise<T> {
  const res = await fetch(path, {
    method: 'GET',
    credentials: 'same-origin',
    headers: { Accept: 'application/json' },
  })
  if (res.status === 401 && !isPublicLinkRoute()) redirectToLogin()
  if (!res.ok) throw new Error(`Failed to load ${what}`)
  return (await res.json()) as T
}

export interface ListAgentsParams {
  limit?: number
  offset?: number
}

function pageQuery(params: { limit?: number; offset?: number } = {}): string {
  const q = new URLSearchParams()
  if (params.limit !== undefined) q.set('limit', String(params.limit))
  if (params.offset !== undefined) q.set('offset', String(params.offset))
  const s = q.toString()
  return s ? `?${s}` : ''
}

export async function listAgents(params: ListAgentsParams = {}): Promise<Page<AgentOut>> {
  return getJson<Page<AgentOut>>(`/api/agents/${pageQuery(params)}`, 'agents')
}

export async function getAgent(slug: string): Promise<AgentDetailOut> {
  return getJson<AgentDetailOut>(`/api/agents/${encodeURIComponent(slug)}/`, 'agent')
}

export async function listAgentSyncs(
  slug: string,
  params: ListAgentsParams = {},
): Promise<Page<AgentSyncOut>> {
  return getJson<Page<AgentSyncOut>>(
    `/api/agents/${encodeURIComponent(slug)}/syncs/${pageQuery(params)}`,
    'agent syncs',
  )
}

export async function listAgentWorkProducts(
  slug: string,
  params: ListAgentsParams = {},
): Promise<Page<AgentWorkProductOut>> {
  return getJson<Page<AgentWorkProductOut>>(
    `/api/agents/${encodeURIComponent(slug)}/work-products/${pageQuery(params)}`,
    'agent work products',
  )
}

export async function listAgentSkills(slug: string): Promise<AgentSkillOut[]> {
  return getJson<AgentSkillOut[]>(
    `/api/agents/${encodeURIComponent(slug)}/skills/`,
    'agent skills',
  )
}
