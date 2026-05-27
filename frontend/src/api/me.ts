import { apiV2 } from "./client.v2";
import type { components } from "./generated";

export type MeOut = components["schemas"]["MeOut"];

export async function getMe(): Promise<MeOut | null> {
  const { data, error } = await apiV2.GET("/api/v2/me/");
  if (error) return null;
  return data;
}
