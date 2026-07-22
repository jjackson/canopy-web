import { ChatSessionsPanel } from '@/components/chat/ChatSessionsPanel'

/**
 * The session-centric chat home (/w/:workspace/chat). Thin wrapper around the
 * reusable ChatSessionsPanel (also embedded in the supervisor Sessions tab) — find
 * individual sessions to follow up on + "New chat with <agent>". Session-centric,
 * not agent-collapsed: the agent is only how you START a session.
 */
export function ChatListPage() {
  return (
    <div className="mx-auto flex h-full w-full max-w-2xl flex-col p-4">
      <ChatSessionsPanel heading="Chats" />
    </div>
  )
}

export default ChatListPage
