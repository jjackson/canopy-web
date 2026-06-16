import { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";

import { ApiError, getSharedSession } from "../api/sessions";
import type { SharedSession } from "../api/sessions";
import { MessageList } from "../components/transcript/MessageList";
import { conversationOnly } from "../components/transcript/conversation";

type LoadState =
  | { kind: "loading" }
  | { kind: "loaded"; session: SharedSession }
  | { kind: "error"; code: string; message: string };

type ViewMode = "conversation" | "full";

/**
 * Public, read-only view of a shared Claude session.
 *
 * Mounted OUTSIDE AppLayout so anonymous (non-dimagi) visitors can read it
 * without the app chrome's authenticated calls bouncing them to login.
 *
 * Defaults to a clean Conversation view (human prompts + Claude's final reply
 * per turn). The full transcript — every tool call and intermediate step — is
 * one client-side toggle away; no re-fetch, the data is all here.
 */
export default function SessionSharePage() {
  const { token = "" } = useParams();
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [mode, setMode] = useState<ViewMode>("conversation");

  useEffect(() => {
    if (!token) return;
    getSharedSession(token)
      .then((session) => setState({ kind: "loaded", session }))
      .catch((e) => {
        if (e instanceof ApiError) {
          setState({ kind: "error", code: e.code, message: e.message });
        } else {
          setState({ kind: "error", code: "unknown", message: "Failed to load" });
        }
      });
  }, [token]);

  const session = state.kind === "loaded" ? state.session : null;
  const conversation = useMemo(
    () => (session ? conversationOnly(session.messages) : []),
    [session],
  );

  if (state.kind === "loading") {
    return (
      <div className="flex min-h-screen items-center justify-center bg-white">
        <p className="text-zinc-500">Loading shared session…</p>
      </div>
    );
  }

  if (state.kind === "error") {
    const message =
      state.code === "not-found"
        ? "This share link is invalid, has expired, or was revoked."
        : state.message;
    return (
      <div className="flex min-h-screen items-center justify-center bg-white">
        <div className="text-center">
          <p className="text-lg font-medium text-zinc-700">{message}</p>
        </div>
      </div>
    );
  }

  const displayed =
    mode === "conversation" ? conversation : state.session.messages;

  return (
    <div className="min-h-screen bg-white">
      <div className="mx-auto max-w-3xl px-4 py-8">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-xl font-semibold text-zinc-900">
              {state.session.title || "Claude session"}
            </h1>
            <div className="mt-1 flex flex-wrap items-center gap-3 text-xs text-zinc-500">
              <span>Shared session — read only</span>
              {state.session.redaction_count > 0 && (
                <span
                  className="rounded-full bg-amber-50 px-2 py-0.5 text-amber-700"
                  title="Best-effort secret scrub. Not a guarantee — review before sharing widely."
                >
                  {state.session.redaction_count} secret
                  {state.session.redaction_count === 1 ? "" : "s"} redacted
                </span>
              )}
            </div>
          </div>
          <ViewToggle mode={mode} setMode={setMode} />
        </div>

        <div className="mt-6">
          {mode === "conversation" && displayed.length === 0 ? (
            <p className="text-sm text-zinc-500">
              No plain conversation turns found — switch to Full transcript to
              see tool activity.
            </p>
          ) : (
            <MessageList messages={displayed} />
          )}
        </div>
      </div>
    </div>
  );
}

function ViewToggle({
  mode,
  setMode,
}: {
  mode: ViewMode;
  setMode: (m: ViewMode) => void;
}) {
  const base =
    "px-3 py-1 text-xs font-medium transition-colors first:rounded-l-md last:rounded-r-md";
  const on = "bg-zinc-900 text-white";
  const off = "bg-white text-zinc-600 hover:bg-zinc-50";
  return (
    <div className="inline-flex shrink-0 overflow-hidden rounded-md border border-zinc-300">
      <button
        type="button"
        className={`${base} ${mode === "conversation" ? on : off}`}
        onClick={() => setMode("conversation")}
        aria-pressed={mode === "conversation"}
      >
        Conversation
      </button>
      <button
        type="button"
        className={`${base} border-l border-zinc-300 ${mode === "full" ? on : off}`}
        onClick={() => setMode("full")}
        aria-pressed={mode === "full"}
      >
        Full transcript
      </button>
    </div>
  );
}
