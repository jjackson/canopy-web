/**
 * API client for the /api/timeline surface (team-wide activity aggregator).
 *
 * Not in the generated OpenAPI types yet — raw fetch with the same credential
 * conventions as api/ddd.ts. Run `npm run gen:api` to migrate to openapi-fetch.
 */

import { apiUrl } from './base'

export interface TimelineEvent {
  subsystem: string
  kind: string
  at: string
  title: string
  summary: string | null
  project_slug: string | null
  actor: string | null
  href: string
  external: boolean
  icon: string | null
  id: string
}

export interface TimelineSubsystem {
  key: string
  label: string
}

export interface TimelineResponse {
  events: TimelineEvent[]
  subsystems: TimelineSubsystem[]
  next_before: string | null
}

export interface ListTimelineParams {
  subsystem?: string
  limit?: number
  before?: string
}

async function getJson<T>(url: string): Promise<T> {
  const resp = await fetch(apiUrl(url), { credentials: 'same-origin' })
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

export function listTimeline(params: ListTimelineParams = {}): Promise<TimelineResponse> {
  const q = new URLSearchParams()
  if (params.subsystem) q.set('subsystem', params.subsystem)
  if (params.limit) q.set('limit', String(params.limit))
  if (params.before) q.set('before', params.before)
  const suffix = q.toString() ? `?${q.toString()}` : ''
  return getJson(`/api/timeline/${suffix}`)
}
