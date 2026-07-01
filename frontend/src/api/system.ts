/**
 * API client for /api/system — the canopy capability catalog (skills / agents /
 * commands) read from the bundled plugin.
 *
 * Raw fetch with the same credential conventions as api/timeline.ts. Not in the
 * generated OpenAPI types yet — run `npm run gen:api` to migrate to openapi-fetch.
 */

import { apiUrl } from './base'

export type CapabilityKind = 'skill' | 'agent' | 'command'

export interface CapabilityItem {
  name: string
  kind: CapabilityKind
  family: string
  display_name: string
  description: string
}

export interface CapabilityDetail extends CapabilityItem {
  body: string
}

export interface CapabilityCatalog {
  items: CapabilityItem[]
  families: string[]
  counts: Record<string, number>
  plugin_version: string | null
  warning: string | null
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

export function getCatalog(): Promise<CapabilityCatalog> {
  return getJson('/api/system/overview')
}

export function getCapability(kind: CapabilityKind, name: string): Promise<CapabilityDetail> {
  return getJson(`/api/system/${kind}/${encodeURIComponent(name)}`)
}
