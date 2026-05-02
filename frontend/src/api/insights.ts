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

export interface InsightListParams {
  category?: string
  project?: string
  limit?: number
}

// Category weight for the dashboard "Today's top 3" hero. Higher = more
// urgent to surface. Tuned for the morning-triage flow: ship gaps and
// opportunities are time-sensitive (a release, a CWS review, an upstream PR
// is about to do something) and warrant jumping the queue. Hygiene and
// pattern are real but rarely "do today". Stale gets the lowest weight
// because by definition nothing is racing.
const CATEGORY_RANK: Record<string, number> = {
  ship_gap: 4,
  opportunity: 3,
  pattern: 2,
  hygiene: 2,
  stale: 1,
}

// Pick the top N insights for the home-dashboard hero. Sort key:
//   1. Category weight (CATEGORY_RANK; unknown/null -> 0)
//   2. Recency (newer first)
export function rankInsights(insights: Insight[], limit = 3): Insight[] {
  return [...insights]
    .sort((a, b) => {
      const aw = CATEGORY_RANK[parseInsightCategory(a.content) ?? ''] ?? 0
      const bw = CATEGORY_RANK[parseInsightCategory(b.content) ?? ''] ?? 0
      if (bw !== aw) return bw - aw
      return new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
    })
    .slice(0, limit)
}

// Most recent insight timestamp across the whole feed. Drives the freshness
// chip on the hero — if this is >24h old the user is triaging stale signals
// and we should nudge them to re-run the portfolio sweep.
export function newestInsightTimestamp(insights: Insight[]): string | null {
  if (!insights.length) return null
  return insights.reduce(
    (acc, i) => (acc && acc > i.created_at ? acc : i.created_at),
    insights[0].created_at,
  )
}

export const insightsApi = {
  list: (params: InsightListParams = {}) => {
    const qp = new URLSearchParams()
    if (params.category) qp.set('category', params.category)
    if (params.project) qp.set('project', params.project)
    if (params.limit) qp.set('limit', String(params.limit))
    const qs = qp.toString()
    return request<Insight[]>(`/insights/${qs ? `?${qs}` : ''}`)
  },
  dismiss: (id: number) =>
    request<{ dismissed: number }>(`/insights/${id}/`, { method: 'DELETE' }),
}
