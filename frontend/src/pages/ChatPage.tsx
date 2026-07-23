import { useCallback, useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { ChatPanel, useSessionSocket } from 'canopy-ui/chat'
import { Markdown } from '@/components/Markdown'
import { wsUrl } from '@/lib/wsUrl'
import { getSession, type ChatSessionDetail } from '@/api/chat'

/** Render assistant/system message text through canopy's shared Markdown (the
 *  same renderer used across every AI-output surface — so it picks up remark-gfm
 *  AND remark-breaks, i.e. single newlines become line breaks instead of
 *  collapsing). Injected into the kit via its `renderMarkdown` seam so the kit
 *  itself stays free of react-markdown. */
function renderMarkdown(text: string) {
  return <Markdown className="text-sm leading-relaxed">{text}</Markdown>
}

/**
 * Standalone live-chat route (/w/:workspace/chat/:id). Wires canopy's
 * WebSocket URL + REST session-meta + react-markdown into the reusable
 * `canopy-ui/chat` ChatPanel. All chat state lives in `useSessionSocket`;
 * this page only supplies seams + a minimal title shell.
 */
export function ChatPage() {
  const { id = '' } = useParams()
  const [meta, setMeta] = useState<ChatSessionDetail | null>(null)
  const [metaError, setMetaError] = useState<string | null>(null)

  const socket = useSessionSocket({ sessionId: id, wsUrl })

  useEffect(() => {
    if (!id) return
    setMeta(null)
    setMetaError(null)
    getSession(id)
      .then(setMeta)
      .catch((err: unknown) => {
        setMetaError(err instanceof Error ? err.message : 'session not found')
      })
  }, [id])

  const emptyState = useCallback(
    () => (
      <div className="flex h-full flex-col items-center justify-center gap-1 p-8 text-center text-sm text-muted-foreground">
        <div className="text-foreground">Start the conversation</div>
        <div className="text-xs">Type a message below to begin.</div>
      </div>
    ),
    [],
  )

  const title = meta?.title?.trim() || 'Chat'

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-2 border-b border-border bg-background px-4 py-2">
        <h1 className="truncate text-sm font-semibold text-foreground">{title}</h1>
        {metaError && (
          <span className="text-xs text-muted-foreground">· {metaError}</span>
        )}
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
          emptyState={emptyState()}
        />
      </div>
    </div>
  )
}

export default ChatPage
