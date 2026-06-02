/**
 * API client for the /api/ddd surface (DDD run views).
 *
 * These endpoints aren't in the generated OpenAPI types yet, so we use raw
 * fetch with the same credential conventions as api/reviews.ts. Run
 * `npm run gen:api` after the backend lands to migrate to openapi-fetch.
 */

export type WalkthroughKind = 'html' | 'video'
export type DddLinkKind = 'narrative' | 'companion' | 'reference'

export interface DddNarrativeListItem {
  slug: string
  title: string | null
  phase: string | null
  project_slug: string | null
  run_count: number
  latest_at: string | null
  has_video: boolean
  has_deck: boolean
  has_narrative: boolean
}

export interface DddNarrativeRun {
  run_id: string
  created_at: string | null
  latest_at: string | null
  status: string | null
  gate: string | null
  scene_count: number
  has_video: boolean
  has_deck: boolean
}

export interface DddNarrativeDetail {
  slug: string
  title: string | null
  story: string | null
  phase: string | null
  project_slug: string | null
  runs: DddNarrativeRun[]
}

export interface DddRunArtifact {
  id: string
  title: string
  kind: WalkthroughKind
  role: string | null
  content_url: string
  viewer_url: string
  duration_sec: number | null
}

export interface DddRunArtifactRef {
  id: string
  title: string
  kind: WalkthroughKind
  role: string | null
  created_at: string
  viewer_url: string
}

export interface DddNarration {
  scene?: number
  id?: string
  title?: string
  persona?: string
  provenance?: string
  text: string
  // features and other fields may be present; kept open.
  [k: string]: unknown
}

export interface DddRunNarrative {
  run_id: string
  gate: string
  title: string | null
  story: string | null
  narration: DddNarration[]
  personas: Record<string, { name?: string; role?: string; color?: string; org?: string }>
  why_brief: Record<string, unknown> | null
}

export interface DddLink {
  label: string
  url: string
  kind: DddLinkKind
}

export interface DddPreviousRun {
  run_id: string
  latest_at: string | null
}

export interface DddRunPackage {
  run_id: string
  narrative_slug: string
  created_at: string | null
  latest_at: string | null
  phase: string | null
  video: DddRunArtifact | null
  deck: DddRunArtifact | null
  narrative: DddRunNarrative | null
  links: DddLink[]
  all_artifacts: DddRunArtifactRef[]
  previous_runs: DddPreviousRun[]
}

async function getJson<T>(url: string): Promise<T> {
  const resp = await fetch(url, { credentials: 'same-origin' })
  if (!resp.ok) {
    let detail = ''
    try {
      detail = (await resp.json())?.detail ?? ''
    } catch {
      /* ignore */
    }
    throw new Error(detail || `Request failed (${resp.status})`)
  }
  return resp.json() as Promise<T>
}

export interface ListNarrativesParams {
  project?: string
  mine?: boolean
}

export function listNarratives(
  params: ListNarrativesParams = {},
): Promise<DddNarrativeListItem[]> {
  const q = new URLSearchParams()
  if (params.project) q.set('project', params.project)
  if (params.mine) q.set('mine', 'true')
  const suffix = q.toString() ? `?${q.toString()}` : ''
  return getJson(`/api/ddd/narratives/${suffix}`)
}

export function getNarrative(slug: string): Promise<DddNarrativeDetail> {
  return getJson(`/api/ddd/narratives/${encodeURIComponent(slug)}/`)
}

export function getRun(runId: string): Promise<DddRunPackage> {
  return getJson(`/api/ddd/runs/${encodeURIComponent(runId)}/`)
}
