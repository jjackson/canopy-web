import { describe, expect, it } from "vitest";
import {
  backfillAction,
  restToKitMessage,
  shouldShowLoadFull,
} from "./chatPageLogic";
import type { ChatSessionDetail } from "@/api/chat";

describe("restToKitMessage", () => {
  it("maps a REST MessageOut into the kit Message shape as complete", () => {
    const rest: ChatSessionDetail["messages"][number] = {
      turn_index: 7,
      role: "assistant",
      plaintext: "hello",
      content: { text: "hello" },
      created_at: "2026-07-23T00:00:00Z",
    };
    expect(restToKitMessage(rest)).toEqual({
      id: "t7",
      turn_index: 7,
      role: "assistant",
      content: { text: "hello" },
      plaintext: "hello",
      status: "complete",
      error_detail: null,
      started_at: null,
      completed_at: "2026-07-23T00:00:00Z",
      created_at: "2026-07-23T00:00:00Z",
    });
  });

  it("gives every mapped row a synthetic id distinct from a real WS pk", () => {
    const rest: ChatSessionDetail["messages"][number] = {
      turn_index: 3,
      role: "user",
      plaintext: "hi",
      content: {},
      created_at: "2026-07-23T00:00:00Z",
    };
    // The kit dedupes prepended history by turn_index, not id — but the id
    // must still never collide with a real WS message pk.
    expect(restToKitMessage(rest).id).toBe("t3");
  });
});

describe("backfillAction", () => {
  it("maps ready -> reload-now", () => {
    expect(backfillAction("ready")).toBe("reload-now");
  });

  it("maps requested -> reload-after-delay", () => {
    expect(backfillAction("requested")).toBe("reload-after-delay");
  });

  it("maps unavailable -> unavailable", () => {
    expect(backfillAction("unavailable")).toBe("unavailable");
  });

  it("degrades an unrecognized status to an immediate reload", () => {
    expect(backfillAction("something-new")).toBe("reload-now");
  });
});

describe("shouldShowLoadFull", () => {
  const base = { hasMoreBefore: false, historyUnavailable: false };

  // REGRESSION (found on prod): a runner-discovered session whose history is
  // still on the laptop has ZERO server Message rows, so it rendered "Start the
  // conversation" with no way to pull its transcript. The offer must NOT depend
  // on messages already being on screen.
  it("offers Load full for a runner session with no messages yet", () => {
    expect(shouldShowLoadFull({ ...base, origin: "runner" })).toBe(true);
  });

  it("does not offer it for a web session", () => {
    expect(shouldShowLoadFull({ ...base, origin: "web" })).toBe(false);
  });

  it("defers to Load earlier when the server holds more than the window", () => {
    expect(
      shouldShowLoadFull({ ...base, origin: "runner", hasMoreBefore: true }),
    ).toBe(false);
  });

  it("stays hidden once history is known unavailable", () => {
    expect(
      shouldShowLoadFull({
        ...base,
        origin: "runner",
        historyUnavailable: true,
      }),
    ).toBe(false);
  });

  it("is hidden before the session meta loads (origin null/undefined)", () => {
    expect(shouldShowLoadFull({ ...base, origin: null })).toBe(false);
    expect(shouldShowLoadFull({ ...base, origin: undefined })).toBe(false);
  });
});
