import { useCallback, useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { ChatPanel, useSessionSocket } from 'canopy-ui/chat'
import { wsUrl } from '@/lib/wsUrl'
import { getSession, type ChatSessionDetail } from '@/api/chat'

/** Render assistant/system markdown with the same token-based prose styling
 *  used elsewhere in canopy (see ShareoutsPage). Injected into the kit so the
 *  kit itself stays free of react-markdown. */
function renderMarkdown(text: string) {
  return (
    <div
      className="
        text-sm leading-relaxed
        [&_p]:my-1.5 [&_p]:text-inherit
        [&_ul]:my-1.5 [&_ul]:list-disc [&_ul]:pl-5 [&_ul]:space-y-1
        [&_ol]:my-1.5 [&_ol]:list-decimal [&_ol]:pl-5 [&_ol]:space-y-1
        [&_li]:pl-0.5
        [&_h1]:text-base [&_h1]:font-semibold [&_h1]:mt-2 [&_h1]:mb-1
        [&_h2]:text-sm [&_h2]:font-semibold [&_h2]:mt-2 [&_h2]:mb-1
        [&_h3]:text-sm [&_h3]:font-semibold [&_h3]:mt-2 [&_h3]:mb-1
        [&_strong]:font-semibold
        [&_a]:text-primary [&_a]:underline [&_a]:underline-offset-2
        [&_pre]:my-2 [&_pre]:overflow-x-auto [&_pre]:rounded [&_pre]:bg-background [&_pre]:p-2 [&_pre]:text-xs
        [&_code]:rounded [&_code]:bg-background/60 [&_code]:px-1 [&_code]:py-0.5 [&_code]:text-[0.85em]
        [&_pre_code]:bg-transparent [&_pre_code]:p-0
      "
    >
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
    </div>
  )
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
