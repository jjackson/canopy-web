import { apiV2 } from "./client.v2";
import type { components } from "./generated";

export type Schedule = components["schemas"]["ScheduleOut"];
export type ScheduleIn = components["schemas"]["ScheduleIn"];
export type SchedulePatch = components["schemas"]["SchedulePatch"];

export async function listSchedules(slug: string): Promise<Schedule[]> {
  const { data, error } = await apiV2.GET("/api/agents/{slug}/schedules/", {
    params: { path: { slug } },
  });
  if (error) throw new Error("Failed to load schedules");
  return data.items as Schedule[];
}

export async function createSchedule(
  slug: string,
  body: ScheduleIn,
): Promise<Schedule> {
  const { data, error } = await apiV2.POST("/api/agents/{slug}/schedules/", {
    params: { path: { slug } },
    body,
  });
  if (error) throw new Error("Failed to create schedule");
  return data as unknown as Schedule;
}

export async function updateSchedule(
  slug: string,
  id: number,
  body: SchedulePatch,
): Promise<Schedule> {
  const { data, error } = await apiV2.PATCH(
    "/api/agents/{slug}/schedules/{schedule_id}",
    {
      params: { path: { slug, schedule_id: id } },
      body,
    },
  );
  if (error) throw new Error("Failed to update schedule");
  return data as unknown as Schedule;
}

export async function deleteSchedule(slug: string, id: number): Promise<void> {
  const { error } = await apiV2.DELETE(
    "/api/agents/{slug}/schedules/{schedule_id}",
    {
      params: { path: { slug, schedule_id: id } },
    },
  );
  if (error) throw new Error("Failed to delete schedule");
}

export async function runScheduleNow(
  slug: string,
  id: number,
): Promise<Schedule> {
  const { data, error } = await apiV2.POST(
    "/api/agents/{slug}/schedules/{schedule_id}/run-now",
    {
      params: { path: { slug, schedule_id: id } },
    },
  );
  if (error) throw new Error("Failed to run schedule");
  return data as unknown as Schedule;
}

export async function previewCron(
  slug: string,
  cron: string,
  timezone: string,
): Promise<string[]> {
  const { data, error } = await apiV2.POST(
    "/api/agents/{slug}/schedules/preview",
    {
      params: { path: { slug } },
      body: { cron, timezone },
    },
  );
  if (error) throw new Error("Failed to preview schedule");
  return data.next_runs as string[];
}
