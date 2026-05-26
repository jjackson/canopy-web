const BASE = '/api'

function getCsrfToken(): string {
  const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/)
  return match ? decodeURIComponent(match[1]) : ''
}

function redirectToLogin(): never {
  const next = encodeURIComponent(window.location.pathname + window.location.search)
  window.location.href = `/accounts/google/login/?next=${next}`
  throw new Error('Redirecting to login')
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const method = (options?.method || 'GET').toUpperCase()
  const headers: Record<string, string> = {
    ...(options?.headers as Record<string, string> | undefined),
  }
  // Don't force Content-Type for FormData — the browser sets it with boundary.
  const isForm = options?.body instanceof FormData
  if (!isForm && method !== 'GET' && method !== 'HEAD') {
    headers['Content-Type'] = 'application/json'
  }
  if (method !== 'GET' && method !== 'HEAD' && method !== 'OPTIONS') {
    const token = getCsrfToken()
    if (token) headers['X-CSRFToken'] = token
  }
  const resp = await fetch(`${BASE}${path}`, {
    credentials: 'same-origin',
    ...options,
    headers,
  })
  if (resp.status === 401) redirectToLogin()
  if (resp.status === 204) return undefined as T
  const data = await resp.json()
  if (!data.success) throw new Error(data.error?.message || 'Request failed')
  return data.data as T
}

export type WalkthroughKind = 'html' | 'video'
export type WalkthroughVisibility = 'private' | 'link'

export interface WalkthroughListItem {
  id: string
  title: string
  description: string
  kind: WalkthroughKind
  project_slug: string | null
  visibility: WalkthroughVisibility
  owner_email: string
  size_bytes: number
  duration_sec: number | null
  created_at: string
  updated_at: string
}

export interface WalkthroughDetail extends WalkthroughListItem {
  share_token: string | null
  content_type: string
  is_owner: boolean
}

export interface WalkthroughListFilters {
  project?: string
  kind?: WalkthroughKind
  mine?: boolean
}

export async function listWalkthroughs(
  filters: WalkthroughListFilters = {},
): Promise<WalkthroughListItem[]> {
  const params = new URLSearchParams()
  if (filters.project) params.set('project', filters.project)
  if (filters.kind) params.set('kind', filters.kind)
  if (filters.mine) params.set('mine', 'true')
  const qs = params.toString()
  return request<WalkthroughListItem[]>(`/walkthroughs/${qs ? `?${qs}` : ''}`)
}

export async function getWalkthrough(id: string): Promise<WalkthroughDetail> {
  return request<WalkthroughDetail>(`/walkthroughs/${id}/`)
}

export interface PatchWalkthroughInput {
  title?: string
  description?: string
  project_slug?: string | null
  visibility?: WalkthroughVisibility
}

export async function patchWalkthrough(
  id: string,
  patch: PatchWalkthroughInput,
): Promise<WalkthroughDetail> {
  return request<WalkthroughDetail>(`/walkthroughs/${id}/`, {
    method: 'PATCH',
    body: JSON.stringify(patch),
  })
}

export async function deleteWalkthrough(id: string): Promise<void> {
  await request<void>(`/walkthroughs/${id}/`, { method: 'DELETE' })
}

export async function rotateWalkthroughToken(
  id: string,
): Promise<{ share_token: string }> {
  return request<{ share_token: string }>(
    `/walkthroughs/${id}/rotate-token/`,
    { method: 'POST' },
  )
}

export function walkthroughContentUrl(
  id: string,
  shareToken: string | null,
): string {
  const t = shareToken ? `?t=${encodeURIComponent(shareToken)}` : ''
  return `/w/${id}/content${t}`
}
