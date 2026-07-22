/**
 * Client for the live chat surface (/api/chat).
 *
 * Plain fetch (mirrors src/api/sessions.ts) rather than the generated
 * openapi-fetch client — the ChatPage only needs create/get/list, and the
 * live transcript arrives over the WebSocket (apps/chat consumer), not REST.
 * CSRF is attached for mutating calls; response shapes reuse the generated
 * OpenAPI schema so the two can't drift.
 */

import type { components } from "./generated";
import { apiUrl, getCsrfToken } from "./base";

export type ChatSession = components["schemas"]["SessionOut"];
export type ChatSessionDetail = components["schemas"]["SessionDetailOut"];

export class ChatApiError extends Error {
  code: string;
  status: number;
  constructor(status: number, code: string, message: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const method = (init.method ?? "GET").toUpperCase();
  const headers = new Headers(init.headers);
  if (!["GET", "HEAD", "OPTIONS"].includes(method)) {
    const token = getCsrfToken();
    if (token) headers.set("X-CSRFToken", token);
  }
  const resp = await fetch(apiUrl(path), {
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
    throw new ChatApiError(
      resp.status,
      code,
      body.detail || body.title || "Request failed",
    );
  }
  return body as T;
}

export interface CreateSessionInput {
  title?: string;
  agentSlug?: string;
  metadata?: Record<string, unknown>;
}

export function createSession(
  input: CreateSessionInput = {},
): Promise<ChatSession> {
  return request<ChatSession>("/api/chat/", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      title: input.title ?? "",
      agent_slug: input.agentSlug ?? null,
      metadata: input.metadata ?? {},
    }),
  });
}

export function getSession(id: string): Promise<ChatSessionDetail> {
  return request<ChatSessionDetail>(`/api/chat/${encodeURIComponent(id)}`);
}

export function listSessions(): Promise<ChatSession[]> {
  return request<ChatSession[]>("/api/chat/");
}
