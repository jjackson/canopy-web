import { describe, expect, it } from "vitest"
import type { Message } from "./protocol"
import { prependHistory } from "./history"

function msg(turn_index: number, plaintext = `m${turn_index}`): Message {
  return {
    id: `t${turn_index}`, turn_index, role: "user", content: {}, plaintext,
    status: "complete", error_detail: null, started_at: null, completed_at: null,
    created_at: "",
  }
}

describe("prependHistory", () => {
  it("prepends older messages ahead of current, chronological", () => {
    const current = [msg(30), msg(31)]
    const older = [msg(28), msg(29)]
    expect(prependHistory(current, older).map((m) => m.turn_index)).toEqual([28, 29, 30, 31])
  })

  it("dedupes on turn_index (an overlapping page is not double-inserted)", () => {
    const current = [msg(30), msg(31)]
    const older = [msg(29), msg(30)] // 30 overlaps
    expect(prependHistory(current, older).map((m) => m.turn_index)).toEqual([29, 30, 31])
  })

  it("returns the same reference when older is empty", () => {
    const current = [msg(30)]
    expect(prependHistory(current, [])).toBe(current)
  })

  it("returns the same reference when every older row already exists", () => {
    const current = [msg(30), msg(31)]
    expect(prependHistory(current, [msg(30)])).toBe(current)
  })
})
