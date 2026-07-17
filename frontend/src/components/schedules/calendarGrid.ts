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
  const weekStartMidnight = cols[0].date;
  for (const item of items) {
    for (const iso of item.fires) {
      const when = new Date(iso);
      // days since the week's Monday, by LOCAL calendar-date components — not
      // a raw millisecond delta, which breaks on any week containing a DST
      // transition (a 23h or 25h local day makes the /86_400_000 divide land
      // on the wrong column for every day after the transition).
      const dayIdx = localDayIndex(when, weekStartMidnight);
      if (dayIdx >= 0 && dayIdx < 7) cols[dayIdx].fires.push({ when, item });
    }
  }
  for (const c of cols) c.fires.sort((a, b) => a.when.getTime() - b.when.getTime());
  return cols;
}

/** Whole local-calendar-day distance between `when` and `weekStart`, DST-safe.
 * Built from each Date's LOCAL Y/M/D (not the UTC getters) via `Date.UTC`,
 * which always yields exactly-24h days — so the difference divided by
 * 86_400_000 is an exact integer regardless of DST transitions in between. */
function localDayIndex(when: Date, weekStart: Date): number {
  const a = Date.UTC(when.getFullYear(), when.getMonth(), when.getDate());
  const b = Date.UTC(weekStart.getFullYear(), weekStart.getMonth(), weekStart.getDate());
  return Math.round((a - b) / 86_400_000);
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
