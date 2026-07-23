/**
 * Pure helpers for ChatPage's REST<->kit wiring — split out of the component
 * so the conversion + the "Load full session" state machine unit-test without
 * mounting React or a WebSocket.
 */

import type { Message } from "canopy-ui/chat";
import type { ChatSessionDetail } from "@/api/chat";

/**
 * A REST `MessageOut` (turn_index/role/plaintext/content/created_at) -> the
 * kit's `Message` shape. Synthetic id (`t<turn_index>`) + `status: "complete"`
 * — `prependHistory` dedupes by `turn_index`, so a synthetic-id row never
 * collides with the WS row of the same index.
 */
export function restToKitMessage(
  m: ChatSessionDetail["messages"][number],
): Message {
  return {
    id: `t${m.turn_index}`,
    turn_index: m.turn_index,
    role: m.role as Message["role"],
    content: m.content,
    plaintext: m.plaintext,
    status: "complete",
    error_detail: null,
    started_at: null,
    completed_at: m.created_at,
    created_at: m.created_at,
  };
}

/**
 * What "Load full session" should do next, given a `BackfillStateOut.status`:
 * - `ready`       — the server already has the full transcript; reload now.
 * - `requested`   — the runner was just asked; give it a beat to land, then reload.
 * - `unavailable` — no runner to ask; show the offline/history-unavailable banner.
 * Any other/unknown status degrades to an immediate reload rather than silently
 * treating it as unavailable.
 */
export type BackfillAction = "reload-now" | "reload-after-delay" | "unavailable";

export function backfillAction(status: string): BackfillAction {
  if (status === "unavailable") return "unavailable";
  if (status === "requested") return "reload-after-delay";
  return "reload-now";
}
