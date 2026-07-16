import type { ScheduleWeekItem } from "@/api/schedules";

export interface BucketedFire {
  /** The fire instant, as a Date (rendered in the viewer's local tz). */
  when: Date;
  item: ScheduleWeekItem;
}

export interface DayColumn {
  /** 0 = Monday … 6 = Sunday. */
  index: number;
  /** Local midnight of this day. */
  date: Date;
  /** Fires that land on this day, ascending by time. */
  fires: BucketedFire[];
}

/** Drop every fire of every item into its local-day column. `weekStart` is the
 * Monday the grid is showing; columns are Mon..Sun in the VIEWER's local tz
 * (the fires cross the wire as UTC and are compared in local time here). */
export function bucketByDay(items: ScheduleWeekItem[], weekStart: Date): DayColumn[] {
  const cols: DayColumn[] = Array.from({ length: 7 }, (_, i) => {
    const d = new Date(weekStart);
    d.setDate(d.getDate() + i);
    d.setHours(0, 0, 0, 0);
    return { index: i, date: d, fires: [] };
  });
  const weekStartMidnight = new Date(cols[0].date);
  for (const item of items) {
    for (const iso of item.fires) {
      const when = new Date(iso);
      // days since the week's Monday, in local time
      const dayIdx = Math.floor((startOfLocalDay(when).getTime() - weekStartMidnight.getTime()) / 86_400_000);
      if (dayIdx >= 0 && dayIdx < 7) cols[dayIdx].fires.push({ when, item });
    }
  }
  for (const c of cols) c.fires.sort((a, b) => a.when.getTime() - b.when.getTime());
  return cols;
}

function startOfLocalDay(d: Date): Date {
  const x = new Date(d);
  x.setHours(0, 0, 0, 0);
  return x;
}

export interface Filters {
  agent: string | null;
  workspace: string | null;
}

/** Client-side filter over the fetched week — instant, no refetch. */
export function matchesFilters(item: ScheduleWeekItem, f: Filters): boolean {
  if (f.agent && item.schedule.agent_slug !== f.agent) return false;
  if (f.workspace && item.workspace_slug !== f.workspace) return false;
  return true;
}
