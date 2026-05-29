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

export interface ReviewFeature {
  id: string
  description: string
  verify: string
}

export interface ReviewNarrationItem {
  scene: number
  id: string
  /** Story-beat title (DDD v3). Falls back to "Scene N" when absent. */
  title?: string
  /** Persona key on screen for this beat (DDD v3). Maps into request_json.personas. */
  persona?: string
  text: string
  features?: ReviewFeature[]
}

export interface ReviewPersona {
  name: string
  role: string
  color: string
  intro: string
}

export interface ReviewVideo {
  walkthrough_id?: string
  url?: string
}

export interface ReviewSceneActionability {
  score: number
  missed: string[]
}

export interface ReviewActionability {
  overall_score: number
  per_scene: Record<string, ReviewSceneActionability>
}

export interface ReviewRequestJson {
  schema_version: number
  run_id: string
  gate: string
  video?: ReviewVideo
  decisions: ReviewDecision[]
  narration: ReviewNarrationItem[]
  /** The cohesive demo narrative — the whole story the scenes decompose (DDD v3). */
  narrative?: string
  /** Persona key -> details, so the surface can show who is on screen each beat. */
  personas?: Record<string, ReviewPersona>
  autonomous_audit: string[]
  actionability?: ReviewActionability | null
  /**
   * Optional pre-set build order — a sequence of scene ids indicating the
   * tackle order the reviewer should start from. When absent, the editor
   * defaults to the narration order.
   */
  build_order?: string[] | null
}

// ---------------------------------------------------------------------------
// Submit payload — new "edited_scenes" contract
// ---------------------------------------------------------------------------

export interface ReviewSubmittedFeature {
  id: string
  description: string
  verify: string
  feedback: string
}

export interface ReviewSubmittedScene {
  id: string
  title: string
  narration: string
  deleted: boolean
  features: ReviewSubmittedFeature[]
  feedback: string
}

export interface ReviewSubmitPayload {
  decisions: Record<string, string>
  /** Legacy field — kept for backwards-compat read; send is now edited_scenes */
  narration_edits?: Record<string, string>
  edited_scenes?: ReviewSubmittedScene[]
  overall_feedback?: string
  /**
   * The reviewer's chosen build sequence — an ordered list of scene ids
   * indicating the order they intend to tackle the scenes when building.
   * Independent of the video/narration order.
   */
  build_order?: string[]
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
