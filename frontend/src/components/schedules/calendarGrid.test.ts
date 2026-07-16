import { describe, it, expect } from "vitest";
import { bucketByDay, matchesFilters } from "./calendarGrid";
import type { ScheduleWeekItem } from "@/api/schedules";

function item(name: string, agent: string, ws: string, fires: string[]): ScheduleWeekItem {
  return {
    // only the fields the helpers read need to be real
    schedule: { name, agent_slug: agent } as ScheduleWeekItem["schedule"],
    workspace_slug: ws,
    fires,
  } as ScheduleWeekItem;
}

describe("bucketByDay", () => {
  it("drops each fire into its local-day column (Mon-indexed)", () => {
    // Week of Mon 2026-07-13, all constructed from LOCAL date parts (not a
    // UTC-Z literal) so the test's expectations hold under any machine
    // timezone, not just UTC — a hardcoded "...T00:00:00Z" weekStart lands on
    // the PREVIOUS local calendar day in any negative-offset zone (e.g.
    // America/Denver), which is exactly the off-by-one this suite guards
    // against. Fires are serialized to ISO (UTC-on-the-wire) to mirror what
    // the API actually sends, then bucketByDay converts back to local time.
    const weekStart = new Date(2026, 6, 13); // local Mon 2026-07-13 00:00
    const monFire = new Date(2026, 6, 13, 9, 0, 0).toISOString();
    const wedFire = new Date(2026, 6, 15, 9, 0, 0).toISOString();
    const items = [item("Daily", "eva", "alpha", [monFire, wedFire])];
    const cols = bucketByDay(items, weekStart);
    expect(cols).toHaveLength(7);
    expect(cols[0].fires).toHaveLength(1); // Monday
    expect(cols[2].fires).toHaveLength(1); // Wednesday
    expect(cols[1].fires).toHaveLength(0); // Tuesday
    // each bucketed fire carries its source item so a chip can render agent + open the editor
    expect(cols[0].fires[0].item.schedule.name).toBe("Daily");
  });
});

describe("matchesFilters", () => {
  const it0 = item("A", "eva", "alpha", []);
  it("passes when no filter is set", () => {
    expect(matchesFilters(it0, { agent: null, workspace: null })).toBe(true);
  });
  it("filters by agent", () => {
    expect(matchesFilters(it0, { agent: "eva", workspace: null })).toBe(true);
    expect(matchesFilters(it0, { agent: "hal", workspace: null })).toBe(false);
  });
  it("filters by workspace", () => {
    expect(matchesFilters(it0, { agent: null, workspace: "alpha" })).toBe(true);
    expect(matchesFilters(it0, { agent: null, workspace: "beta" })).toBe(false);
  });
});
