import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { Plus } from 'lucide-react'
import {
  Button,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from 'canopy-ui/ui'
import { createSession, listSessions, type ChatSession } from '@/api/chat'
import { listAgents, type AgentOut } from '@/api/agents'
import { relativeTime } from '@/components/activity/turnLog'

/**
 * The session-centric chat home (/w/:workspace/chat). Find/follow-up individual
 * sessions to continue from any device, and start a new one via "new chat with
 * <agent>". Deliberately NOT collapsed into per-agent views — the agent is only
 * how you START a session; the session is the durable, findable thing.
 */
export function ChatListPage() {
  const { workspace = '' } = useParams()
  const navigate = useNavigate()
  const [sessions, setSessions] = useState<ChatSession[]>([])
  const [agents, setAgents] = useState<AgentOut[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)

  useEffect(() => {
    let live = true
    setLoading(true)
    Promise.allSettled([listSessions(), listAgents({ limit: 100 })]).then(
      ([s, a]) => {
        if (!live) return
        if (s.status === 'fulfilled') setSessions(s.value)
        else setError(s.reason instanceof Error ? s.reason.message : 'failed to load sessions')
        if (a.status === 'fulfilled') setAgents(a.value.items)
        setLoading(false)
      },
    )
    return () => {
      live = false
    }
  }, [])

  const agentName = useMemo(() => {
    const by = new Map(agents.map((a) => [a.slug, a.name]))
    return (slug: string | null) => (slug ? by.get(slug) ?? slug : null)
  }, [agents])

  const startChat = useCallback(
    (agentSlug?: string) => {
      setCreating(true)
      createSession({ agentSlug })
        .then((s) => navigate(`/w/${workspace}/chat/${s.id}`))
        .catch((err: unknown) => {
          setError(err instanceof Error ? err.message : 'could not start chat')
          setCreating(false)
        })
    },
    [navigate, workspace],
  )

  const now = new Date()

  return (
    <div className="mx-auto flex h-full w-full max-w-2xl flex-col">
      <div className="flex items-center justify-between gap-2 border-b border-border px-4 py-3">
        <h1 className="text-base font-semibold text-foreground">Chats</h1>
        <DropdownMenu>
          <DropdownMenuTrigger render={<Button size="sm" disabled={creating} />}>
            <Plus className="mr-1 h-4 w-4" />
            New chat
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="max-h-80 overflow-y-auto">
            <DropdownMenuLabel>New chat with…</DropdownMenuLabel>
            {agents.length === 0 && (
              <DropdownMenuItem disabled>No agents in this workspace</DropdownMenuItem>
            )}
            {agents.map((a) => (
              <DropdownMenuItem key={a.slug} onSelect={() => startChat(a.slug)}>
                {a.name}
              </DropdownMenuItem>
            ))}
            <DropdownMenuSeparator />
            <DropdownMenuItem onSelect={() => startChat(undefined)}>
              Blank chat (no agent)
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto">
        {error && <div className="px-4 py-3 text-sm text-destructive">{error}</div>}
        {loading ? (
          <div className="px-4 py-6 text-sm text-muted-foreground">Loading sessions…</div>
        ) : sessions.length === 0 ? (
          <div className="flex flex-col items-center justify-center gap-1 px-4 py-16 text-center">
            <div className="text-sm text-foreground">No chats yet</div>
            <div className="text-xs text-muted-foreground">
              Start one with “New chat” — pick an agent to talk to.
            </div>
          </div>
        ) : (
          <ul className="divide-y divide-border">
            {sessions.map((s) => {
              const who = agentName(s.agent_slug)
              return (
                <li key={s.id}>
                  <Link
                    to={`/w/${workspace}/chat/${s.id}`}
                    className="flex items-center justify-between gap-3 px-4 py-3 hover:bg-muted"
                  >
                    <div className="min-w-0">
                      <div className="truncate text-sm font-medium text-foreground">
                        {s.title?.trim() || 'Untitled chat'}
                      </div>
                      <div className="truncate text-xs text-muted-foreground">
                        {who ? `with ${who}` : 'no agent'}
                        {s.status !== 'active' ? ` · ${s.status}` : ''}
                      </div>
                    </div>
                    <div className="shrink-0 text-xs text-muted-foreground">
                      {relativeTime(s.created_at, now)}
                    </div>
                  </Link>
                </li>
              )
            })}
          </ul>
        )}
      </div>
    </div>
  )
}

export default ChatListPage
