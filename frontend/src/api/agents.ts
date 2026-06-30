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

import { apiUrl } from './base'

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
  task_count: number
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

export type AgentTaskStatus = 'suggested' | 'in_progress' | 'done' | 'declined'

export interface AgentTaskLink {
  label: string
  url: string
}

export interface AgentTaskOut {
  id: number
  agent_slug: string
  ext_id: string
  title: string // the OUTCOME
  next_action: string // the single concrete next step, verb-first
  status: AgentTaskStatus
  owner: string // the human stakeholder — NEVER the agent
  assigned: string // who the next action waits on — the agent ("Echo") OR a person
  confidence: string // 'high' | 'low' | '' (for suggested items)
  due: string | null
  links: AgentTaskLink[]
  notes: string
  rationale: string // why this task is on the board — shown as a muted "Why: …" line
  source_url: string // the originating thread/doc, surfaced as a "source ↗" chip
  plan: string // Echo's intended approach, if any
  position: number
  updated_at: string
}

// ── Command queue ────────────────────────────────────────────────────────────
// Actions a human takes on a task POST a command; Echo drains pending commands
// on its next turn. `created_by` is filled server-side — never send it.

export type AgentCommandKind =
  | 'accept'
  | 'decline'
  | 'dispatch'
  | 'done'
  | 'reassign'
  | 'edit'
  | 'comment'

export interface AgentCommandOut {
  id: number
  agent_slug: string
  task_id: number | null
  task_ext_id: string // the task's stable sheet id ('' if the task was deleted)
  task_title: string // the task's outcome, for activity rows
  kind: AgentCommandKind
  payload: Record<string, unknown>
  status: string // 'pending' | 'applied' | 'dismissed'
  created_by: string // who clicked it (email)
  result_note: string // what Echo actually did, set when the command is applied
  created_at: string
  applied_at: string | null // when Echo drained/applied it
}

export interface PostCommandResult {
  command: AgentCommandOut
  task: AgentTaskOut
}

// ── "Needs you" supervisor inbox ─────────────────────────────────────────────
// The typed/ranked list of what the human must act on, computed server-side so
// CLI agents / open claws can query "what needs the human" the same way the UI
// does. Bands: review → question → notify.

export type NeedsYouType = 'review' | 'question' | 'notify'

export interface NeedsYouItem {
  type: NeedsYouType
  ref_kind: 'task' | 'sync' | 'work_product'
  ref_id: number
  title: string
  subtitle: string
  url: string
  created_at: string
}

export interface NeedsYouOut {
  agent_slug: string
  waiting_count: number // gated (review + question) items — the "N waiting on you" badge
  items: NeedsYouItem[]
}

// Mirrors client.v2's auth: anonymous 401s on a non-public route bounce to the
// Google login flow; everything else surfaces as a thrown Error.
function redirectToLogin(): never {
  const next = encodeURIComponent(window.location.pathname + window.location.search)
  window.location.href = `${import.meta.env.BASE_URL.replace(/\/$/, '')}/accounts/google/login/?next=${next}`
  throw new Error('Redirecting to login')
}

function isPublicLinkRoute(): boolean {
  const base = import.meta.env.BASE_URL.replace(/\/$/, '')
  const p = window.location.pathname.slice(base.length)
  return p.startsWith('/review/') || p.startsWith('/w/') || p.startsWith('/share/')
}

async function getJson<T>(path: string, what: string): Promise<T> {
  const res = await fetch(apiUrl(path), {
    method: 'GET',
    credentials: 'same-origin',
    headers: { Accept: 'application/json' },
  })
  if (res.status === 401 && !isPublicLinkRoute()) redirectToLogin()
  if (!res.ok) throw new Error(`Failed to load ${what}`)
  return (await res.json()) as T
}

function readCookie(name: string): string {
  return document.cookie.match(new RegExp(`(?:^|;\\s*)${name}=([^;]+)`))?.[1] ?? ''
}

// Django's session auth (Ninja) enforces CSRF on unsafe methods. Read the
// csrftoken cookie (bootstrapping it from /api/csrf/ if absent) and send it.
async function csrfToken(): Promise<string> {
  let token = readCookie('csrftoken')
  if (!token) {
    await fetch(apiUrl('/api/csrf/'), { credentials: 'same-origin' })
    token = readCookie('csrftoken')
  }
  return token ? decodeURIComponent(token) : ''
}

async function postJson<T>(path: string, body: unknown, what: string): Promise<T> {
  const token = await csrfToken()
  const res = await fetch(apiUrl(path), {
    method: 'POST',
    credentials: 'same-origin',
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
      ...(token ? { 'X-CSRFToken': token } : {}),
    },
    body: JSON.stringify(body),
  })
  if (res.status === 401 && !isPublicLinkRoute()) redirectToLogin()
  if (!res.ok) throw new Error(`Failed to ${what}`)
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

// The typed/ranked "what needs the human" list (review → question → notify).
export async function getNeedsYou(slug: string): Promise<NeedsYouOut> {
  return getJson<NeedsYouOut>(
    `/api/agents/${encodeURIComponent(slug)}/needs-you`,
    'needs-you inbox',
  )
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

// Plain array, not paginated.
export async function listAgentTasks(slug: string): Promise<AgentTaskOut[]> {
  return getJson<AgentTaskOut[]>(
    `/api/agents/${encodeURIComponent(slug)}/tasks/`,
    'agent tasks',
  )
}

// POST an action onto a task's command queue. `created_by` is server-filled.
// accept/dispatch/done take no payload; decline → {reason}; reassign →
// {assignee}; edit → {next_action}; comment → {note}.
export async function postTaskCommand(
  slug: string,
  taskId: number,
  kind: AgentCommandKind,
  payload?: Record<string, unknown>,
): Promise<PostCommandResult> {
  return postJson<PostCommandResult>(
    `/api/agents/${encodeURIComponent(slug)}/tasks/${taskId}/commands`,
    { kind, payload: payload ?? {} },
    `${kind} task`,
  )
}

// List the agent's commands. Pass `status` to filter ('pending' for the queue
// Echo will drain; omit for the full activity stream — newest first).
export async function listAgentCommands(
  slug: string,
  status?: string,
): Promise<AgentCommandOut[]> {
  const q = status ? `?status=${encodeURIComponent(status)}` : ''
  return getJson<AgentCommandOut[]>(
    `/api/agents/${encodeURIComponent(slug)}/commands${q}`,
    'agent commands',
  )
}

// Pending commands queued for the agent to drain next turn.
export async function listPendingCommands(slug: string): Promise<AgentCommandOut[]> {
  return listAgentCommands(slug, 'pending')
}
