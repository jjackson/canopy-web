import { useCallback, useEffect, useMemo, useState } from 'react'
import { useParams } from 'react-router-dom'
import { ChatPanel, useSessionSocket } from 'canopy-ui/chat'
import { Markdown } from '@/components/Markdown'
import { wsUrl } from '@/lib/wsUrl'
import {
  getSession,
  listMessages,
  attachSession,
  detachSession,
  requestBackfill,
  type ChatSessionDetail,
} from '@/api/chat'
import { backfillAction, restToKitMessage } from './chatPageLogic'

/** Render assistant/system message text through canopy's shared Markdown (the
 *  same renderer used across every AI-output surface — so it picks up remark-gfm
 *  AND remark-breaks, i.e. single newlines become line breaks instead of
 *  collapsing). Injected into the kit via its `renderMarkdown` seam so the kit
 *  itself stays free of react-markdown. */
function renderMarkdown(text: string) {
  return <Markdown className="text-sm leading-relaxed">{text}</Markdown>
}

const BACKFILL_SETTLE_DELAY_MS = 1200

/**
 * Standalone live-chat route (/w/:workspace/chat/:id). Wires canopy's
 * WebSocket URL + REST session-meta/history/liveness + react-markdown into the
 * reusable `canopy-ui/chat` ChatPanel. All live chat state lives in
 * `useSessionSocket`; this page supplies seams (attach/detach, scroll-back,
 * full backfill, running/idle) + a minimal title shell.
 */
export function ChatPage() {
  const { id = '' } = useParams()
  const [meta, setMeta] = useState<ChatSessionDetail | null>(null)
  const [metaError, setMetaError] = useState<string | null>(null)
  // Scroll-back cursor, seeded from the REST detail (the WS `session.state`
  // snapshot doesn't carry it — it's frozen to the tail page it was built from).
  const [hasMoreBefore, setHasMoreBefore] = useState(false)
  const [oldestTurn, setOldestTurn] = useState<number | null>(null)
  const [loadingEarlier, setLoadingEarlier] = useState(false)
  const [historyUnavailable, setHistoryUnavailable] = useState(false)

  const socket = useSessionSocket({ sessionId: id, wsUrl })

  // Session meta + scroll-back cursor seed.
  useEffect(() => {
    if (!id) return
    setMeta(null)
    setMetaError(null)
    setHistoryUnavailable(false)
    getSession(id)
      .then((m) => {
        setMeta(m)
        setHasMoreBefore(m.has_more_before)
        setOldestTurn(m.oldest_loaded_turn_index ?? null)
      })
      .catch((err: unknown) => {
        setMetaError(err instanceof Error ? err.message : 'session not found')
      })
  }, [id])

  // Attach-on-open / detach-on-unmount. Composes safely with the WS-lifecycle
  // attach the consumer already does on connect/disconnect (see the task brief
  // note): the viewer registry counts both, 0<->1 edges are idempotent, and a
  // web session with no bound runner sees this as a safe no-op
  // ({streaming: false}). React StrictMode's mount/unmount/remount double-invoke
  // is fine here — attach and detach are each individually idempotent.
  useEffect(() => {
    if (!id) return
    void attachSession(id).catch(() => {
      /* non-fatal: a failed attach just means no bound runner to notify */
    })
    return () => {
      void detachSession(id).catch(() => {
        /* non-fatal */
      })
    }
  }, [id])

  const loadEarlier = useCallback(async () => {
    if (oldestTurn == null || loadingEarlier) return
    setLoadingEarlier(true)
    try {
      const page = await listMessages(id, oldestTurn)
      if (page.messages.length > 0) {
        socket.prependMessages(page.messages.map(restToKitMessage))
        setOldestTurn(page.messages[0].turn_index)
      }
      // A local (origin=runner) session with no server rows yet returns an
      // empty page with has_more_before=false — history lives on the runner,
      // so fall through to offering the full backfill instead.
      setHasMoreBefore(page.messages.length > 0 ? page.has_more_before : false)
    } catch {
      /* keep what's shown; the button stays available to retry */
    } finally {
      setLoadingEarlier(false)
    }
  }, [id, oldestTurn, loadingEarlier, socket])

  const loadFull = useCallback(async () => {
    setHistoryUnavailable(false)
    try {
      const res = await requestBackfill(id)
      const action = backfillAction(res.status)
      if (action === 'unavailable') {
        setHistoryUnavailable(true)
        return
      }
      // reload-now = already server-full; reload-after-delay = the runner is
      // shipping it — give it a beat to land before pulling the full session.
      if (action === 'reload-after-delay') {
        await new Promise((r) => setTimeout(r, BACKFILL_SETTLE_DELAY_MS))
      }
      const full = await getSession(id, { full: true })
      socket.prependMessages(full.messages.map(restToKitMessage))
      setHasMoreBefore(false)
      setOldestTurn(full.oldest_loaded_turn_index ?? null)
    } catch {
      setHistoryUnavailable(true)
    }
  }, [id, socket])

  const emptyState = useMemo(
    () => (
      <div className="flex h-full flex-col items-center justify-center gap-1 p-8 text-center text-sm text-muted-foreground">
        <div className="text-foreground">Start the conversation</div>
        <div className="text-xs">Type a message below to begin.</div>
      </div>
    ),
    [],
  )

  const showLoadFull =
    !hasMoreBefore &&
    !historyUnavailable &&
    meta?.origin === 'runner' &&
    socket.state.messages.length > 0

  const historySlot = (
    <div className="flex flex-col items-center gap-1 py-2">
      {historyUnavailable && (
        <p className="rounded-md border border-warning/30 bg-warning/10 px-3 py-1.5 text-[12px] text-warning">
          Full history unavailable — runner offline. Showing the latest messages.
        </p>
      )}
      {hasMoreBefore && (
        <button
          type="button"
          onClick={() => void loadEarlier()}
          disabled={loadingEarlier}
          className="rounded-md border border-border bg-card px-3 py-1 text-[12px] text-foreground-secondary hover:bg-muted disabled:opacity-50"
        >
          {loadingEarlier ? 'Loading…' : 'Load earlier'}
        </button>
      )}
      {showLoadFull && (
        <button
          type="button"
          onClick={() => void loadFull()}
          className="rounded-md border border-border bg-card px-3 py-1 text-[12px] text-foreground-secondary hover:bg-muted"
        >
          Load full session
        </button>
      )}
    </div>
  )

  const title = meta?.title?.trim() || 'Chat'

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-2 border-b border-border bg-background px-4 py-2">
        <h1 className="truncate text-sm font-semibold text-foreground">{title}</h1>
        {/* Running/idle indicator, from the unified session's liveness fields. */}
        {meta?.running ? (
          <span className="flex shrink-0 items-center gap-1 text-[12px] font-medium text-success">
            <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-success" />
            running{meta.runner_name ? ` · ${meta.runner_name}` : ''}
          </span>
        ) : meta?.runner_name ? (
          <span className="shrink-0 text-[12px] text-muted-foreground">
            idle · {meta.runner_name}
          </span>
        ) : null}
        {metaError && <span className="text-xs text-muted-foreground">· {metaError}</span>}
      </div>
      <div className="min-h-0 flex-1">
        <ChatPanel
          state={socket.state}
          connected={socket.connected}
          currentUserId={socket.state.current_user_id}
          onSend={socket.sendChat}
          onStop={socket.stopChat}
          onUpdateDraft={socket.updateDraft}
          onTakeOver={socket.takeOverDraft}
          onDiscard={socket.discardDraft}
          renderMarkdown={renderMarkdown}
          emptyState={emptyState}
          historySlot={historySlot}
        />
      </div>
    </div>
  )
}

export default ChatPage
