const BASE = '/api'

function getCsrfToken(): string {
  const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/)
  return match ? decodeURIComponent(match[1]) : ''
}

function redirectToLogin(): never {
  const next = encodeURIComponent(window.location.pathname + window.location.search)
  window.location.href = `/accounts/google/login/?next=${next}`
  // window.location.href is async; throw so callers don't see an undefined return.
  throw new Error('Redirecting to login')
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const method = (options?.method || 'GET').toUpperCase()
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options?.headers as Record<string, string> | undefined),
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

  if (resp.status === 401) {
    redirectToLogin()
  }

  const data = await resp.json()
  if (!data.success) throw new Error(data.error?.message || 'Request failed')
  return data.data
}

async function requestRaw(path: string, options?: RequestInit): Promise<Response> {
  const method = (options?.method || 'GET').toUpperCase()
  const headers: Record<string, string> = {
    ...(options?.headers as Record<string, string> | undefined),
  }
  if (method !== 'GET' && method !== 'HEAD' && method !== 'OPTIONS') {
    const token = getCsrfToken()
    if (token) headers['X-CSRFToken'] = token
  }
  return fetch(`${BASE}${path}`, { credentials: 'same-origin', ...options, headers })
}

export type MeResponse = {
  email: string
  name: string
  avatar_url: string
}

export const api = {
  createCollection: (name: string, description = '') =>
    request('/collections/', { method: 'POST', body: JSON.stringify({ name, description }) }),
  addSource: (collectionId: number, source: { source_type: string; title?: string; content: string }) =>
    request(`/collections/${collectionId}/sources/`, { method: 'POST', body: JSON.stringify(source) }),
  getCollection: (id: number) => request(`/collections/${id}/`),
  getWorkspace: (sessionId: number) => request(`/workspace/${sessionId}/`),
  editSkill: (sessionId: number, edit: object, structural: boolean) =>
    request(`/workspace/${sessionId}/edit/`, { method: 'PATCH', body: JSON.stringify({ edit, structural }) }),
  publishSkill: (sessionId: number) =>
    request(`/workspace/${sessionId}/publish/`, { method: 'POST' }),
  getSkills: (sort = '-updated_at') => request(`/skills/?sort=${sort}`),
  getSkill: (id: number) => request(`/skills/${id}/`),
  generateAdapter: (skillId: number, runtime: string) =>
    request(`/skills/${skillId}/adapter/`, { method: 'POST', body: JSON.stringify({ runtime }) }),
  getEvalSuite: (skillId: number) => request(`/evals/${skillId}/`),
  runEval: (skillId: number) => request(`/evals/${skillId}/run/`, { method: 'POST' }),
  getEvalHistory: (skillId: number) => request(`/evals/${skillId}/history/`),
  updateEvalCase: (skillId: number, caseId: number, data: object) =>
    request(`/evals/${skillId}/cases/${caseId}/`, { method: 'PATCH', body: JSON.stringify(data) }),
  deleteEvalCase: (skillId: number, caseId: number) =>
    request(`/evals/${skillId}/cases/${caseId}/`, { method: 'DELETE' }),
  analyzeWorkspace: (collectionId: number) =>
    request<{ session_id: number; status: string; approach: Record<string, unknown>; eval_cases: Record<string, unknown>[] }>(
      `/workspace/analyze/${collectionId}/`,
      { method: 'POST' },
    ),

  // Auth / session
  bootstrapCsrf: () => request<{ ok: boolean }>('/csrf/'),
  me: async (): Promise<MeResponse | null> => {
    const resp = await requestRaw('/me/')
    if (resp.status === 401) return null
    const json = await resp.json()
    return json as MeResponse
  },

  // AI backend
  getAiStatus: () => request<{
    backend: string; ready: boolean; detail: string; setup_hint: string | null;
  }>('/ai/status/'),
  switchAiBackend: (backend: 'api' | 'cli') =>
    request<{ backend: string }>('/ai/switch/', { method: 'POST', body: JSON.stringify({ backend }) }),

  // Auth flow
  authStart: () => request<{
    auth_url: string | null; token: string | null; status: string;
  }>('/ai/auth/start/', { method: 'POST' }),

  authComplete: (code: string) => request<{
    token_preview: string; status: string;
  }>('/ai/auth/complete/', { method: 'POST', body: JSON.stringify({ code }) }),

  authPoll: () => request<{
    active: boolean; authenticated: boolean; elapsed_seconds?: number;
  }>('/ai/auth/poll/'),
}
