import type { SessionMessage } from "../../api/sessions";

// Harness-authored "user" lines that aren't things the human typed.
const NOISE_PREFIXES = [
  "<system-reminder",
  "<command-name",
  "<command-message",
  "<command-args",
  "<local-command-stdout",
  "<local-command-stderr",
  "<local-command-caveat",
  "<task-notification",
  "<system>",
  "Caveat:",
  "[Request interrupted",
];

function isNoiseUser(text: string): boolean {
  const t = text.replace(/^\s+/, "");
  return NOISE_PREFIXES.some((p) => t.startsWith(p));
}

/**
 * Reduce a raw transcript to a readable conversation: what the human typed,
 * plus the FINAL assistant text of each turn.
 *
 * Drops tool_use / tool_result / system rows and harness-noise user lines,
 * and collapses each run of consecutive assistant messages to its last one
 * (the intermediate "thinking, then call a tool" fragments are hidden; the
 * final summary Claude presented at the end of the turn is kept).
 *
 * Client-side only — the full transcript stays available via the toggle.
 */
export function conversationOnly(messages: SessionMessage[]): SessionMessage[] {
  const kept: SessionMessage[] = [];
  for (const m of messages) {
    if (m.role === "user") {
      if (m.plaintext.trim() && !isNoiseUser(m.plaintext)) kept.push(m);
    } else if (m.role === "assistant") {
      if (m.plaintext.trim()) kept.push(m);
    }
    // tool_use / tool_result / system are dropped.
  }

  // Collapse consecutive assistant rows to the last in each run.
  return kept.filter(
    (m, i) =>
      !(
        m.role === "assistant" &&
        i + 1 < kept.length &&
        kept[i + 1].role === "assistant"
      ),
  );
}
