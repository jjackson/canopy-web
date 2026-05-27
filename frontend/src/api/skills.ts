import { apiV2 } from "./client.v2";
import type { components } from "./generated";

export type SkillOut = components["schemas"]["SkillOut"];
export type AdapterOut = components["schemas"]["AdapterOut"];

export async function listSkills(): Promise<SkillOut[]> {
  const { data, error } = await apiV2.GET("/api/skills/");
  if (error) throw new Error("Failed to load skills");
  return data.items as SkillOut[];
}

export async function getSkill(id: number): Promise<SkillOut> {
  const { data, error } = await apiV2.GET("/api/skills/{pk}/", {
    params: { path: { pk: id } },
  });
  if (error) throw new Error("Failed to load skill");
  return data;
}

export async function generateAdapter(
  skillId: number,
  runtime: string,
): Promise<AdapterOut> {
  const { data, error } = await apiV2.POST("/api/skills/{pk}/adapter/", {
    params: { path: { pk: skillId } },
    body: { runtime: runtime as "web" | "claude_code" | "open_claw" },
  });
  if (error) throw new Error("Failed to generate adapter");
  return data;
}
