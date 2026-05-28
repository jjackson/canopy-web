/**
 * API client for the /api/reviews/ surface.
 *
 * The reviews endpoints are not yet in the generated OpenAPI types, so we use
 * raw fetch with the same CSRF + credential conventions as client.v2.ts.
 *
 * Auth strategy mirrors the backend contract:
 *   - Authenticated session users: no extra params required.
 *   - Link-token holders (?t=<share_token>): pass token as query param so the
 *     backend's _token_ok() check succeeds for unauthenticated callers.
 */

function getCsrfToken(): string {
  const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/)
  return match ? decodeURIComponent(match[1]) : ''
}

// ---------------------------------------------------------------------------
// Types (mirrors apps/reviews/schemas.py)
// ---------------------------------------------------------------------------

export type ReviewStatus = 'pending' | 'resolved'
export type ReviewVisibility = 'private' | 'link'

export interface ReviewDecision {
  id: string
  prompt: string
  options: string[]
  recommended: string
  class: string
}

export interface ReviewNarrationItem {
  scene: number
  id: string
  text: string
}

export interface ReviewVideo {
  walkthrough_id?: string
  url?: string
}

export interface ReviewRequestJson {
  schema_version: number
  run_id: string
  gate: string
  video?: ReviewVideo
  decisions: ReviewDecision[]
  narration: ReviewNarrationItem[]
  autonomous_audit: string[]
}

export interface ReviewSubmitPayload {
  decisions: Record<string, string>
  narration_edits: Record<string, string>
}

export interface ReviewDetail {
  id: string
  run_id: string
  gate: string
  status: ReviewStatus
  visibility: ReviewVisibility
  request_json: ReviewRequestJson
  response_json: ReviewSubmitPayload | null
  share_token: string | null
  is_owner: boolean
  created_at: string
  resolved_at: string | null
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function reviewUrl(id: string, token?: string | null): string {
  const t = token ? `?t=${encodeURIComponent(token)}` : ''
  return `/api/reviews/${id}/${t}`
}

function submitUrl(id: string, token?: string | null): string {
  const t = token ? `?t=${encodeURIComponent(token)}` : ''
  return `/api/reviews/${id}/submit/${t}`
}

async function parseResponse<T>(resp: Response): Promise<T> {
  if (!resp.ok) {
    let msg = `Request failed: ${resp.status}`
    try {
      const body = await resp.json()
      if (body?.detail) msg = body.detail
      else if (body?.title) msg = body.title
    } catch {
      // ignore parse failure
    }
    throw new Error(msg)
  }
  return resp.json() as Promise<T>
}

// ---------------------------------------------------------------------------
// API calls
// ---------------------------------------------------------------------------

/** Fetch a review by id. Pass token for link-visibility access. */
export async function getReview(id: string, token?: string | null): Promise<ReviewDetail> {
  const resp = await fetch(reviewUrl(id, token), {
    credentials: 'same-origin',
  })
  return parseResponse<ReviewDetail>(resp)
}

/** Submit decisions + narration edits for a review. */
export async function submitReview(
  id: string,
  payload: ReviewSubmitPayload,
  token?: string | null,
): Promise<ReviewDetail> {
  const csrf = getCsrfToken()
  const resp = await fetch(submitUrl(id, token), {
    method: 'POST',
    credentials: 'same-origin',
    headers: {
      'Content-Type': 'application/json',
      ...(csrf ? { 'X-CSRFToken': csrf } : {}),
    },
    body: JSON.stringify({ response_json: payload }),
  })
  return parseResponse<ReviewDetail>(resp)
}
