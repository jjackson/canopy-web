/**
 * AI backend API — typed wrapper around /api/ai/* endpoints.
 *
 * Shape-adaptation note: the v2 schemas diverge from the legacy DRF responses
 * that page components were written against. Rather than rewrite every consumer
 * right now, this module maps the v2 shapes back to the legacy field names so
 * existing pages keep working. Task 4.3 will clean up the consumers.
 *
 *   v2 AiStatusOut:    { backend, authenticated, detail }
 *   legacy consumers:  { backend, ready, detail, setup_hint }
 *
 *   v2 AiAuthStartOut: { auth_url, state }
 *   legacy consumers:  { auth_url, token, status }
 *
 *   v2 AiAuthCompleteOut: { ok, detail }
 *   legacy consumers:     { token_preview, status }
 *
 *   v2 AiAuthPollOut: { state, detail }
 *   legacy consumers: { active, authenticated, elapsed_seconds }
 */

import { apiV2 } from "./client.v2";

// Legacy shape expected by AppLayout + SettingsPage.
export interface AiStatusLegacy {
  backend: string;
  ready: boolean;
  detail: string;
  setup_hint: string | null;
}

export async function aiStatus(): Promise<AiStatusLegacy> {
  const { data, error } = await apiV2.GET("/api/ai/status/");
  if (error) throw new Error("Failed to load AI status");
  return {
    backend: data.backend,
    ready: data.authenticated,
    detail: data.detail ?? "",
    setup_hint: null,
  };
}

export async function aiSwitch(
  backend: "api" | "cli",
): Promise<{ backend: string }> {
  const { data, error } = await apiV2.POST("/api/ai/switch/", {
    body: { backend },
  });
  if (error) throw new Error("Failed to switch AI backend");
  return { backend: data.backend };
}

// Legacy shape: { auth_url, token, status }
export interface AiAuthStartLegacy {
  auth_url: string | null;
  token: string | null;
  status: string;
}

export async function aiAuthStart(): Promise<AiAuthStartLegacy> {
  const { data, error } = await apiV2.POST("/api/ai/auth/start/");
  if (error) throw new Error("Failed to start auth");
  return {
    auth_url: data.auth_url,
    token: null,
    status: "pending",
  };
}

// Legacy shape: { token_preview, status }
export interface AiAuthCompleteLegacy {
  token_preview: string;
  status: string;
}

export async function aiAuthComplete(code: string): Promise<AiAuthCompleteLegacy> {
  const { data, error } = await apiV2.POST("/api/ai/auth/complete/", {
    body: { code },
  });
  if (error) throw new Error("Failed to complete auth");
  return {
    token_preview: data.detail ?? "",
    status: data.ok ? "complete" : "error",
  };
}

// Legacy shape: { active, authenticated, elapsed_seconds }
export interface AiAuthPollLegacy {
  active: boolean;
  authenticated: boolean;
  elapsed_seconds?: number;
}

export async function aiAuthPoll(): Promise<AiAuthPollLegacy> {
  const { data, error } = await apiV2.GET("/api/ai/auth/poll/");
  if (error) throw new Error("Failed to poll auth");
  return {
    active: data.state === "pending",
    authenticated: data.state === "ok",
  };
}
