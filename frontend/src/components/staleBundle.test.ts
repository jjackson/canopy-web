import { describe, it, expect } from "vitest";
import { shouldReloadForStaleBundle, STALE_RELOAD_WINDOW_MS } from "./staleBundle";

describe("shouldReloadForStaleBundle", () => {
  it("reloads when we have never reloaded (lastReloadAt = 0)", () => {
    expect(shouldReloadForStaleBundle(0, 1_000_000)).toBe(true);
  });

  it("does NOT reload again within the window (we just reloaded and still landed here)", () => {
    const now = 1_000_000;
    expect(shouldReloadForStaleBundle(now - 1, now)).toBe(false);
    expect(shouldReloadForStaleBundle(now - (STALE_RELOAD_WINDOW_MS - 1), now)).toBe(false);
  });

  it("reloads again once the window has fully elapsed (a genuinely new stale deploy later)", () => {
    const now = 1_000_000;
    expect(shouldReloadForStaleBundle(now - (STALE_RELOAD_WINDOW_MS + 1), now)).toBe(true);
  });
});
