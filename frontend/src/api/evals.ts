import { apiV2 } from "./client.v2";
import type { components } from "./generated";

export type EvalSuiteOut = components["schemas"]["EvalSuiteOut"];
export type EvalRunOut = components["schemas"]["EvalRunOut"];
export type EvalCaseOut = components["schemas"]["EvalCaseOut"];

export async function getEvalSuite(skillId: number): Promise<EvalSuiteOut> {
  const { data, error } = await apiV2.GET("/api/v2/evals/{skill_id}/", {
    params: { path: { skill_id: skillId } },
  });
  if (error) throw new Error("Failed to load eval suite");
  return data as unknown as EvalSuiteOut;
}

export async function runEval(skillId: number): Promise<EvalRunOut> {
  const { data, error } = await apiV2.POST("/api/v2/evals/{skill_id}/run/", {
    params: { path: { skill_id: skillId } },
    body: { runtime: "web" },
  });
  if (error) throw new Error("Failed to run eval");
  return data;
}

export async function getEvalHistory(skillId: number): Promise<EvalRunOut[]> {
  const { data, error } = await apiV2.GET("/api/v2/evals/{skill_id}/history/", {
    params: { path: { skill_id: skillId } },
  });
  if (error) throw new Error("Failed to load eval history");
  return data.items as EvalRunOut[];
}

export async function addEvalCase(
  skillId: number,
  evalCase: {
    name: string;
    input_data: Record<string, unknown>;
    expected_output: Record<string, unknown>;
    source_excerpt?: string;
  },
): Promise<EvalCaseOut> {
  const { data, error } = await apiV2.POST("/api/v2/evals/{skill_id}/cases/", {
    params: { path: { skill_id: skillId } },
    body: {
      name: evalCase.name,
      input_data: evalCase.input_data,
      expected_output: evalCase.expected_output,
      source_excerpt: evalCase.source_excerpt ?? "",
    },
  });
  if (error) throw new Error("Failed to add eval case");
  return data;
}

export async function editEvalCase(
  skillId: number,
  caseId: number,
  patch: {
    name?: string | null;
    input_data?: Record<string, unknown> | null;
    expected_output?: Record<string, unknown> | null;
    source_excerpt?: string | null;
  },
): Promise<EvalCaseOut> {
  const { data, error } = await apiV2.PATCH(
    "/api/v2/evals/{skill_id}/cases/{case_id}/",
    {
      params: { path: { skill_id: skillId, case_id: caseId } },
      body: patch,
    },
  );
  if (error) throw new Error("Failed to update eval case");
  return data;
}

export async function deleteEvalCase(
  skillId: number,
  caseId: number,
): Promise<void> {
  const { error } = await apiV2.DELETE(
    "/api/v2/evals/{skill_id}/cases/{case_id}/",
    {
      params: { path: { skill_id: skillId, case_id: caseId } },
    },
  );
  if (error) throw new Error("Failed to delete eval case");
}
