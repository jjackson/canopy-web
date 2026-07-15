import { describe, it, expect, vi, afterEach } from "vitest";
import { describeCron, relative } from "./cronDescribe";

describe("describeCron", () => {
  it("renders a weekly schedule", () => {
    expect(describeCron("0 9 * * 5", "America/New_York")).toBe("Fridays at 09:00 · New York");
  });

  it("renders a monthly schedule", () => {
    expect(describeCron("0 9 1 * *", "America/New_York")).toBe(
      "Day 1 monthly at 09:00 · New York",
    );
  });

  it("renders a daily schedule", () => {
    expect(describeCron("30 6 * * *", "UTC")).toBe("Daily at 06:30 · UTC");
  });

  it("falls back to the raw expression for shapes it cannot name", () => {
    // Always correct, if not always pretty — never claim a wrong cadence.
    expect(describeCron("0 9 * * 1-5", "UTC")).toBe("0 9 * * 1-5 · UTC");
  });
});

describe("relative", () => {
  afterEach(() => vi.useRealTimers());

  it("renders an em dash for no value", () => {
    expect(relative(null)).toBe("—");
  });

  it("renders future days", () => {
    vi.useFakeTimers().setSystemTime(new Date("2026-07-15T12:00:00Z"));
    expect(relative("2026-07-17T13:00:00Z")).toBe("in 2d");
  });

  it("renders past hours", () => {
    vi.useFakeTimers().setSystemTime(new Date("2026-07-15T12:00:00Z"));
    expect(relative("2026-07-15T09:00:00Z")).toBe("3h ago");
  });
});
