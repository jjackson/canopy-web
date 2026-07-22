import {
  useEffect,
  useRef,
  useState,
  type KeyboardEvent,
  type ReactNode,
} from "react";

import type { Draft } from "./protocol";
import { isDraftIdle, msUntilDraftIdle } from "./drafts";
import { Button } from "../ui/button";

interface Props {
  draft: Draft | null;
  currentUserId: number;
  holderIsPresent: boolean;
  isStreaming: boolean;
  streamingMessageId: string | null;
  onUpdate: (body: string) => void;
  onSend: () => void;
  onStop: (messageId: string) => void;
  onTakeOver: () => void;
  /** Optional app-supplied banner rendered above the composer (e.g. an
   *  imported-session note). The kit itself has no CLI-auth banners. */
  banner?: ReactNode;
  /** When set, sending is disabled and this reason is shown as a hint. */
  disabledReason?: string;
}

export function SendBox({
  draft,
  currentUserId,
  holderIsPresent,
  isStreaming,
  streamingMessageId,
  onUpdate,
  onSend,
  onStop,
  onTakeOver,
  banner,
  disabledReason,
}: Props) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  // Force a re-render when the lock transitions from live to idle.
  // Without this, nothing would trigger a re-render exactly at T+2s
  // after the last edit, and another user's UI would stay locked
  // indefinitely until some unrelated event happens to arrive.
  const [, forceTick] = useState(0);

  useEffect(() => {
    if (!draft) return;
    const remaining = msUntilDraftIdle(draft);
    if (remaining === 0) return;
    const t = window.setTimeout(() => forceTick((n) => n + 1), remaining + 10);
    return () => window.clearTimeout(t);
  }, [draft?.last_edit_at, draft]);

  const holderId = draft?.last_editor ?? null;
  const isHolder = holderId != null && holderId === currentUserId;
  const holderIsIdle = isDraftIdle(draft);

  // Gate on draft existence: during the pre-session.state window the
  // textarea would otherwise accept keystrokes that silently drop
  // because the hook's updateDraft no-ops when active_draft is null.
  const canEdit =
    draft != null && (isHolder || holderIsIdle || !holderIsPresent);

  useEffect(() => {
    if (canEdit && !isHolder && textareaRef.current) {
      textareaRef.current.focus();
    }
  }, [canEdit, isHolder]);

  const body = draft?.body ?? "";
  const blocked = Boolean(disabledReason);
  const canSend =
    canEdit && body.trim().length > 0 && !isStreaming && !blocked;

  const handleKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    // `isComposing` is true during IME input (CJK, etc.). Pressing
    // Enter to commit a composition must not send the message.
    const isComposing = (e.nativeEvent as unknown as { isComposing?: boolean })
      .isComposing;
    if (e.key === "Enter" && !e.shiftKey && !isComposing) {
      e.preventDefault();
      if (canSend) onSend();
    }
  };

  const handleStopClick = () => {
    if (streamingMessageId != null) onStop(streamingMessageId);
  };

  const placeholder = !draft
    ? "Connecting…"
    : blocked
      ? disabledReason
      : canEdit
        ? "Type a message… (Enter to send, Shift+Enter for newline)"
        : "Another teammate is editing…";

  return (
    <div className="border-t border-border bg-background">
      {banner}
      <div className="p-2">
        <textarea
          ref={textareaRef}
          value={body}
          disabled={!canEdit || blocked}
          onChange={(e) => onUpdate(e.target.value)}
          onKeyDown={handleKey}
          placeholder={placeholder}
          rows={3}
          className="w-full resize-none rounded-md border border-input bg-transparent p-2 text-sm text-foreground shadow-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:bg-muted disabled:text-muted-foreground"
        />
        <div className="mt-1 flex items-center justify-end gap-2">
          {blocked && (
            <span className="mr-auto text-xs text-muted-foreground">
              {disabledReason}
            </span>
          )}
          {isStreaming ? (
            <Button
              type="button"
              variant="destructive"
              size="sm"
              onClick={handleStopClick}
            >
              stop
            </Button>
          ) : null}
          {!canEdit && holderIsPresent && !holderIsIdle ? (
            <Button type="button" variant="outline" size="sm" onClick={onTakeOver}>
              take over
            </Button>
          ) : null}
          <Button type="button" size="sm" disabled={!canSend} onClick={onSend}>
            send
          </Button>
        </div>
      </div>
    </div>
  );
}
