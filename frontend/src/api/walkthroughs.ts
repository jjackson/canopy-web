import { apiV2 } from "./client.v2";
import type { components } from "./generated";

export type WalkthroughKind = "html" | "video";
export type WalkthroughVisibility = "private" | "link";

export type WalkthroughListItem = components["schemas"]["WalkthroughListItemOut"];
export type WalkthroughDetail = components["schemas"]["WalkthroughDetailOut"];
export type WalkthroughLink = components["schemas"]["WalkthroughLink"];
export type WalkthroughLinkKind = "narrative" | "companion" | "reference";

export interface WalkthroughListFilters {
  project?: string;
  kind?: WalkthroughKind;
  mine?: boolean;
}

export interface PatchWalkthroughInput {
  title?: string;
  description?: string;
  project_slug?: string | null;
  visibility?: WalkthroughVisibility;
}

export async function listWalkthroughs(
  filters: WalkthroughListFilters = {},
): Promise<WalkthroughListItem[]> {
  const { data, error } = await apiV2.GET("/api/walkthroughs/", {
    params: {
      query: {
        ...(filters.project ? { project: filters.project } : {}),
        ...(filters.kind ? { kind: filters.kind } : {}),
        ...(filters.mine ? { mine: "true" } : {}),
      },
    },
  });
  if (error) throw new Error("Failed to load walkthroughs");
  return data as unknown as WalkthroughListItem[];
}

export async function getWalkthrough(id: string): Promise<WalkthroughDetail> {
  const { data, error } = await apiV2.GET("/api/walkthroughs/{wid}/", {
    params: { path: { wid: id } },
  });
  if (error) throw new Error("Failed to load walkthrough");
  return data;
}

export async function patchWalkthrough(
  id: string,
  patch: PatchWalkthroughInput,
): Promise<WalkthroughDetail> {
  const { data, error } = await apiV2.PATCH("/api/walkthroughs/{wid}/", {
    params: { path: { wid: id } },
    body: {
      title: patch.title ?? null,
      description: patch.description ?? null,
      project_slug: patch.project_slug ?? null,
      visibility: patch.visibility ?? null,
    },
  });
  if (error) throw new Error("Failed to update walkthrough");
  return data;
}

export async function deleteWalkthrough(id: string): Promise<void> {
  const { error } = await apiV2.DELETE("/api/walkthroughs/{wid}/", {
    params: { path: { wid: id } },
  });
  if (error) throw new Error("Failed to delete walkthrough");
}

export async function rotateWalkthroughToken(
  id: string,
): Promise<{ share_token: string }> {
  const { data, error } = await apiV2.POST(
    "/api/walkthroughs/{wid}/rotate-token/",
    {
      params: { path: { wid: id } },
    },
  );
  if (error) throw new Error("Failed to rotate token");
  return data;
}

// Multipart upload — openapi-fetch's bodySerializer is used to pass FormData
// directly rather than JSON-encoding the body.
// Note: openapi-fetch types the body as the schema type; we override with
// `unknown` cast + bodySerializer to send raw FormData for multipart.
export async function uploadWalkthrough(
  form: FormData,
): Promise<WalkthroughDetail> {
  const { data, error } = await apiV2.POST("/api/walkthroughs/", {
    // openapi-fetch defaults to JSON; override for multipart so the browser
    // sets the Content-Type boundary automatically.
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    body: form as any,
    bodySerializer: (body: unknown) => body as FormData,
  });
  if (error) throw new Error("Upload failed");
  return data;
}

export function walkthroughContentUrl(
  id: string,
  shareToken: string | null,
): string {
  const t = shareToken ? `?t=${encodeURIComponent(shareToken)}` : "";
  return `/w/${id}/content${t}`;
}
