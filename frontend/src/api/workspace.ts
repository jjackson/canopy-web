/**
 * Workspace API client.
 *
 * JSON endpoints use the typed apiV2 client. The /start/ endpoint
 * streams text/event-stream — openapi-fetch can't model streams, so
 * startWorkspaceStream() uses raw fetch() and returns the Response
 * for the caller to consume as an EventStream.
 */
import { apiV2 } from "./client.v2";
import type { components } from "./generated";

export type WorkspaceSessionListItem = components["schemas"]["WorkspaceSessionListItemOut"];
export type WorkspaceSession = components["schemas"]["WorkspaceSessionOut"];
export type WorkspaceAnalyze = components["schemas"]["WorkspaceAnalyzeOut"];
export type Skill = components["schemas"]["SkillOut"];
export type EditSkillIn = components["schemas"]["EditSkillIn"];
export type PublishSkillIn = components["schemas"]["PublishSkillIn"];

// Re-export legacy names if existing pages import them by other names.
export type WorkspaceSessionOut = WorkspaceSession;

export interface WorkspaceFilters {
  status?: string;
  collection?: number;
  limit?: number;
}

function getCsrfToken(): string {
  const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : "";
}

export async function listWorkspaces(
  filters: WorkspaceFilters = {}
): Promise<WorkspaceSessionListItem[]> {
  const { data, error } = await apiV2.GET("/api/workspace/", {
    params: {
      query: {
        ...(filters.status !== undefined && { status: filters.status }),
        ...(filters.collection !== undefined && { collection: filters.collection }),
        ...(filters.limit !== undefined && { limit: filters.limit }),
      },
    },
  });
  if (error) throw new Error("Failed to load workspace sessions");
  return (data as components["schemas"]["Page_WorkspaceSessionListItemOut_"]).items as WorkspaceSessionListItem[];
}

export async function getWorkspace(sessionId: number): Promise<WorkspaceSession> {
  const { data, error } = await apiV2.GET("/api/workspace/{session_id}/", {
    params: { path: { session_id: sessionId } },
  });
  if (error) throw new Error("Workspace session not found");
  return data as WorkspaceSession;
}

export async function editSkill(
  sessionId: number,
  payload: EditSkillIn
): Promise<WorkspaceSession> {
  const { data, error } = await apiV2.PATCH("/api/workspace/{session_id}/edit/", {
    params: { path: { session_id: sessionId } },
    body: payload,
  });
  if (error) throw new Error("Failed to edit skill");
  return data as WorkspaceSession;
}

export async function publishSkill(
  sessionId: number,
  payload: PublishSkillIn = {}
): Promise<Skill> {
  const { data, error } = await apiV2.POST("/api/workspace/{session_id}/publish/", {
    params: { path: { session_id: sessionId } },
    body: payload,
  });
  if (error) throw new Error("Failed to publish skill");
  return data as Skill;
}

export async function analyzeWorkspace(collectionId: number): Promise<WorkspaceAnalyze> {
  const { data, error } = await apiV2.POST("/api/workspace/analyze/{collection_id}/", {
    params: { path: { collection_id: collectionId } },
  });
  if (error) throw new Error("Workspace analysis failed");
  return data as WorkspaceAnalyze;
}

/**
 * Start a workspace analysis SSE stream.
 *
 * Returns the raw Response whose body is a readable stream emitting
 * text/event-stream frames. The caller is responsible for consuming
 * the stream (e.g. via response.body.getReader()).
 */
export async function startWorkspaceStream(collectionId: number): Promise<Response> {
  const csrf = getCsrfToken();
  return fetch(`/api/workspace/start/${collectionId}/`, {
    method: "POST",
    headers: {
      "X-CSRFToken": csrf,
      Accept: "text/event-stream",
    },
    credentials: "same-origin",
  });
}
