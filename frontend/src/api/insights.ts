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

export interface Insight {
  id: number
  project_slug: string
  project_name: string
  context_type: string
  content: string
  source: string
  created_at: string
}

export type InsightCategory = 'ship_gap' | 'hygiene' | 'pattern' | 'stale' | 'opportunity'

export function parseInsightCategory(content: string): InsightCategory | null {
  const match = content.match(/^\[(\w+)\]/)
  if (!match) return null
  return match[1] as InsightCategory
}

export function parseInsightBody(content: string): string {
  return content.replace(/^\[\w+\]\s*/, '')
}

export const insightsApi = {
  list: (category?: string, limit?: number) => {
    const params = new URLSearchParams()
    if (category) params.set('category', category)
    if (limit) params.set('limit', String(limit))
    const qs = params.toString()
    return request<Insight[]>(`/insights/${qs ? `?${qs}` : ''}`)
  },
  dismiss: (id: number) =>
    request<{ dismissed: number }>(`/insights/${id}/`, { method: 'DELETE' }),
}
