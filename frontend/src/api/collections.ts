import { apiV2 } from "./client.v2";
import type { components } from "./generated";

export type CollectionOut = components["schemas"]["CollectionOut"];
export type SourceOut = components["schemas"]["SourceOut"];

export async function createCollection(
  name: string,
  description = "",
): Promise<CollectionOut> {
  const { data, error } = await apiV2.POST("/api/collections/", {
    body: { name, description },
  });
  if (error) throw new Error("Failed to create collection");
  return data as unknown as CollectionOut;
}

export async function getCollection(id: number): Promise<CollectionOut> {
  const { data, error } = await apiV2.GET("/api/collections/{pk}/", {
    params: { path: { pk: id } },
  });
  if (error) throw new Error("Failed to load collection");
  return data as unknown as CollectionOut;
}

export async function addSource(
  collectionId: number,
  source: { source_type: string; title?: string; content: string },
): Promise<SourceOut> {
  const { data, error } = await apiV2.POST("/api/collections/{pk}/sources/", {
    params: { path: { pk: collectionId } },
    body: {
      source_type: source.source_type as
        | "slack"
        | "transcript"
        | "document"
        | "text",
      title: source.title ?? "",
      content: source.content,
    },
  });
  if (error) throw new Error("Failed to add source");
  return data;
}
