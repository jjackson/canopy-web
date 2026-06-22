/**
 * Client for the shared-session surface (/api/sessions + /api/share).
 *
 * Deliberately uses plain fetch rather than the generated openapi-fetch
 * client: the public /share/{token} read must work for anonymous visitors
 * (no login bounce), and these routes don't need the typed-paths machinery.
 * CSRF is attached for mutating calls, matching client.v2.ts.
 */

export type SessionVisibility = "private" | "link";
export type MessageRole =
  | "user"
  | "assistant"
  | "system"
  | "tool_use"
  | "tool_result";

export interface SessionMessage {
  turn_index: number;
  role: MessageRole;
  content: Record<string, unknown>;
  plaintext: string;
}

export interface SessionListItem {
  slug: string;
  title: string;
  project_slug: string | null;
  visibility: SessionVisibility;
  owner_email: string;
  message_count: number;
  redaction_count: number;
  share_token: string | null;
  is_owner: boolean;
  created_at: string;
  updated_at: string;
}

/** One arc section in the public view — a member session's turn-synthesis. */
export interface SharedSection {
  heading: string;
  redaction_count: number;
  messages: SessionMessage[];
}

/**
 * Public read-only payload for /api/share/{token}. Discriminated by `kind`:
 * a single `session` (messages populated) or an `arc` (sections populated).
 */
export interface SharedView {
  kind: "session" | "arc";
  title: string;
  redaction_count: number;
  messages: SessionMessage[]; // session kind
  sections: SharedSection[]; // arc kind
}

export class ApiError extends Error {
  code: string;
  status: number;
  constructor(status: number, code: string, message: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

function csrfToken(): string {
  const m = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
  return m ? decodeURIComponent(m[1]) : "";
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const method = (init.method ?? "GET").toUpperCase();
  const headers = new Headers(init.headers);
  if (!["GET", "HEAD", "OPTIONS"].includes(method)) {
    const token = csrfToken();
    if (token) headers.set("X-CSRFToken", token);
  }
  const resp = await fetch(path, {
    ...init,
    method,
    headers,
    credentials: "same-origin",
  });
  if (resp.status === 204) return undefined as T;
  const body = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    // RFC 7807 problem+json: derive a stable code from the type URI tail.
    const type = typeof body.type === "string" ? body.type : "";
    const code = type.split("/").pop() || "error";
    throw new ApiError(resp.status, code, body.detail || body.title || "Request failed");
  }
  return body as T;
}

/** Public, read-only — works for anonymous visitors with a valid token.
 * Resolves either a single shared session or a multi-session arc. */
export function getShared(token: string): Promise<SharedView> {
  return request<SharedView>(`/api/share/${encodeURIComponent(token)}`);
}

export function listMySessions(): Promise<SessionListItem[]> {
  return request<SessionListItem[]>("/api/sessions/");
}

export function rotateSessionToken(slug: string): Promise<{ share_token: string }> {
  return request(`/api/sessions/${slug}/rotate-token`, { method: "POST" });
}

export function setSessionVisibility(
  slug: string,
  visibility: SessionVisibility,
): Promise<SessionListItem> {
  return request<SessionListItem>(`/api/sessions/${slug}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ visibility }),
  });
}

export function deleteSession(slug: string): Promise<void> {
  return request<void>(`/api/sessions/${slug}`, { method: "DELETE" });
}

export function shareUrl(token: string): string {
  return `${window.location.origin}/share/${token}`;
}
