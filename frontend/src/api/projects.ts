const BASE = '/api'

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const resp = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options?.headers },
    ...options,
  })
  const data = await resp.json()
  if (!data.success) throw new Error(data.error?.message || 'Request failed')
  return data.data
}

export interface ProjectContext {
  content: string
  source: string
  created_at: string
}

export interface ProjectContextEntry {
  id: number
  context_type: string
  content: string
  source: string
  created_at: string
}

export interface Project {
  id: number
  name: string
  slug: string
  repo_url: string
  deploy_url: string
  visibility: string
  status: string
  latest_context: Record<string, ProjectContext>
  created_at: string
  updated_at: string
}

export interface ProjectDetail {
  id: number
  name: string
  slug: string
  repo_url: string
  deploy_url: string
  visibility: string
  status: string
  contexts: ProjectContextEntry[]
  created_at: string
  updated_at: string
}

export const projectsApi = {
  list: () => request<Project[]>('/projects/'),
  get: (slug: string) => request<ProjectDetail>(`/projects/${slug}/`),
  create: (data: { name: string; slug: string; repo_url?: string; deploy_url?: string; visibility?: string; status?: string }) =>
    request<Project>('/projects/', { method: 'POST', body: JSON.stringify(data) }),
  update: (slug: string, data: Partial<{ name: string; repo_url: string; deploy_url: string; status: string; visibility: string }>) =>
    request<Project>(`/projects/${slug}/`, { method: 'PATCH', body: JSON.stringify(data) }),
  delete: (slug: string) =>
    request<{ deleted: string }>(`/projects/${slug}/`, { method: 'DELETE' }),
  postContext: (slug: string, data: { context_type: string; content: string; source: string }) =>
    request<ProjectContextEntry>(`/projects/${slug}/context/`, { method: 'POST', body: JSON.stringify(data) }),
  getContext: (slug: string, type?: string) =>
    request<ProjectContextEntry[]>(`/projects/${slug}/context/${type ? `?type=${type}` : ''}`),
  getLatestContext: (slug: string) =>
    request<Record<string, ProjectContext>>(`/projects/${slug}/context/latest/`),
}
