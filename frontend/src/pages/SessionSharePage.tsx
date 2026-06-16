import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";

import { ApiError, getSharedSession } from "../api/sessions";
import type { SharedSession } from "../api/sessions";
import { MessageList } from "../components/transcript/MessageList";

type LoadState =
  | { kind: "loading" }
  | { kind: "loaded"; session: SharedSession }
  | { kind: "error"; code: string; message: string };

/**
 * Public, read-only view of a shared Claude session.
 *
 * Mounted OUTSIDE AppLayout so anonymous (non-dimagi) visitors can read it
 * without the app chrome's authenticated calls bouncing them to login.
 *
 * Renders exactly what was uploaded. The uploader reduces transcripts to a
 * clean conversation (prompts + final replies) client-side by default, so
 * tool noise never reaches here; `--full` uploads the raw transcript instead.
 */
export default function SessionSharePage() {
  const { token = "" } = useParams();
  const [state, setState] = useState<LoadState>({ kind: "loading" });

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

  const { session } = state;

  return (
    <div className="min-h-screen bg-white">
      <div className="mx-auto max-w-3xl px-4 py-8">
        <h1 className="text-xl font-semibold text-zinc-900">
          {session.title || "Claude session"}
        </h1>
        <div className="mt-1 flex flex-wrap items-center gap-3 text-xs text-zinc-500">
          <span>Shared session — read only</span>
          {session.redaction_count > 0 && (
            <span
              className="rounded-full bg-amber-50 px-2 py-0.5 text-amber-700"
              title="Best-effort secret scrub. Not a guarantee — review before sharing widely."
            >
              {session.redaction_count} secret
              {session.redaction_count === 1 ? "" : "s"} redacted
            </span>
          )}
        </div>
        <div className="mt-6">
          <MessageList messages={session.messages} />
        </div>
      </div>
    </div>
  );
}
