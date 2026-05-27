/**
 * Debug session minting.
 *
 * Hits the bare Django view at /api/debug/mint-session/ to mint a
 * short-lived session cookie for an AI assistant. NOT a Ninja v2
 * endpoint — it manipulates SessionStore directly. Out-of-band.
 */
function getCsrfToken(): string {
  const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/)
  return match ? decodeURIComponent(match[1]) : ''
}

export interface MintDebugSessionResponse {
  cookie_name: string
  cookie_value: string
  origin: string
  expires_at: string
  ttl_seconds: number
  email: string
  curl_example: string
}

export async function mintDebugSession(ttlSeconds?: number): Promise<MintDebugSessionResponse> {
  const response = await fetch('/api/debug/mint-session/', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': getCsrfToken(),
    },
    credentials: 'same-origin',
    body: JSON.stringify(ttlSeconds ? { ttl_seconds: ttlSeconds } : {}),
  })
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    throw new Error(body.detail || `Mint failed: ${response.status}`)
  }
  return (await response.json()) as MintDebugSessionResponse
}
