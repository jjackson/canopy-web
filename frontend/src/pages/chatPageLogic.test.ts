import { describe, expect, it } from "vitest";
import { backfillAction, restToKitMessage } from "./chatPageLogic";
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
