import { apiV2 } from "./client.v2";
import type { components } from "./generated";

export type Insight = components["schemas"]["InsightOut"];

export type InsightCategory = 'ship_gap' | 'hygiene' | 'pattern' | 'stale' | 'opportunity' | 'alignment'

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

export interface InsightClearParams {
  source?: string
  category?: string
  project?: string
  older_than_days?: number
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
  alignment: 3,
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
  list: async (params: InsightListParams = {}): Promise<Insight[]> => {
    const { data, error } = await apiV2.GET("/api/insights/", {
      params: {
        query: {
          ...(params.category ? { category: params.category } : {}),
          ...(params.project ? { project: params.project } : {}),
          ...(params.limit !== undefined ? { limit: params.limit } : {}),
        },
      },
    });
    if (error) throw new Error("Failed to load insights");
    return data.items as Insight[];
  },
  dismiss: async (id: number): Promise<{ dismissed: number }> => {
    const { data, error } = await apiV2.DELETE("/api/insights/{pk}/", {
      params: { path: { pk: id } },
    });
    if (error) throw new Error("Failed to dismiss insight");
    return data as { dismissed: number };
  },
  clear: async (params: InsightClearParams = {}): Promise<{ cleared: number }> => {
    const { data, error } = await apiV2.POST("/api/insights/clear/", {
      body: {
        source: params.source ?? null,
        category: params.category ?? null,
        project: params.project ?? null,
        older_than_days: params.older_than_days ?? null,
      },
    });
    if (error) throw new Error("Failed to clear insights");
    return data as { cleared: number };
  },
}
