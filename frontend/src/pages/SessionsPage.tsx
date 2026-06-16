import { useCallback, useEffect, useState } from "react";

import {
  deleteSession,
  listMySessions,
  rotateSessionToken,
  setSessionVisibility,
  shareUrl,
} from "../api/sessions";
import type { SessionListItem } from "../api/sessions";

export function SessionsPage() {
  const [sessions, setSessions] = useState<SessionListItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState<string | null>(null);

  const load = useCallback(() => {
    listMySessions()
      .then(setSessions)
      .catch(() => setError("Failed to load sessions"));
  }, []);

  useEffect(load, [load]);

  const copy = async (token: string) => {
    await navigator.clipboard.writeText(shareUrl(token));
    setCopied(token);
    setTimeout(() => setCopied(null), 1500);
  };

  const onRotate = async (slug: string) => {
    await rotateSessionToken(slug);
    load();
  };

  const onToggle = async (s: SessionListItem) => {
    await setSessionVisibility(
      s.slug,
      s.visibility === "link" ? "private" : "link",
    );
    load();
  };

  const onDelete = async (slug: string) => {
    if (!confirm("Delete this shared session? The link will stop working.")) return;
    await deleteSession(slug);
    load();
  };

  if (error) return <div className="p-6 text-red-600">{error}</div>;
  if (sessions === null) return <div className="p-6 text-zinc-500">Loading…</div>;

  return (
    <div className="mx-auto max-w-4xl px-4 py-8">
      <h1 className="text-2xl font-semibold text-zinc-900">Shared sessions</h1>
      <p className="mt-1 text-sm text-zinc-500">
        Claude Code transcripts you've shared. Run{" "}
        <code className="rounded bg-zinc-100 px-1">/canopy:share-session</code> to
        add one.
      </p>

      {sessions.length === 0 ? (
        <p className="mt-8 text-zinc-500">No shared sessions yet.</p>
      ) : (
        <ul className="mt-6 divide-y divide-zinc-200 rounded-lg border border-zinc-200">
          {sessions.map((s) => (
            <li key={s.slug} className="flex items-center gap-4 p-4">
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="truncate font-medium text-zinc-900">
                    {s.title || "Claude session"}
                  </span>
                  <span
                    className={`rounded-full px-2 py-0.5 text-xs ${
                      s.visibility === "link"
                        ? "bg-green-50 text-green-700"
                        : "bg-zinc-100 text-zinc-600"
                    }`}
                  >
                    {s.visibility === "link" ? "link" : "private"}
                  </span>
                  {s.redaction_count > 0 && (
                    <span className="rounded-full bg-amber-50 px-2 py-0.5 text-xs text-amber-700">
                      {s.redaction_count} redacted
                    </span>
                  )}
                </div>
                <div className="mt-0.5 text-xs text-zinc-500">
                  {s.message_count} messages ·{" "}
                  {new Date(s.created_at).toLocaleString()}
                  {s.project_slug ? ` · ${s.project_slug}` : ""}
                </div>
              </div>
              <div className="flex shrink-0 items-center gap-2 text-sm">
                {s.visibility === "link" && s.share_token && (
                  <>
                    <a
                      className="text-zinc-600 underline-offset-2 hover:underline"
                      href={shareUrl(s.share_token)}
                      target="_blank"
                      rel="noreferrer"
                    >
                      Open
                    </a>
                    <button
                      className="text-zinc-600 hover:text-zinc-900"
                      onClick={() => copy(s.share_token!)}
                    >
                      {copied === s.share_token ? "Copied!" : "Copy link"}
                    </button>
                    <button
                      className="text-zinc-600 hover:text-zinc-900"
                      onClick={() => onRotate(s.slug)}
                      title="Invalidate the current link and mint a new one"
                    >
                      Rotate
                    </button>
                  </>
                )}
                <button
                  className="text-zinc-600 hover:text-zinc-900"
                  onClick={() => onToggle(s)}
                >
                  {s.visibility === "link" ? "Make private" : "Make link"}
                </button>
                <button
                  className="text-red-500 hover:text-red-700"
                  onClick={() => onDelete(s.slug)}
                >
                  Delete
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
