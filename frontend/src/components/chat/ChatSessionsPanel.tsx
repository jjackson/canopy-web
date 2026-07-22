import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
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
 * Reusable, CROSS-WORKSPACE chat session surface: a findable list of your chat
 * sessions (continue any from any device) + "New chat with <agent>". Each session
 * links to ITS OWN workspace's chat route, and a new chat is created in the chosen
 * agent's workspace — the fleet spans workspaces. Used by the standalone chat home
 * (/w/:ws/chat) and by the root-scoped supervisor Sessions tab.
 */
export function ChatSessionsPanel({
  agents: agentsProp,
  heading = 'Chats',
  showList = true,
}: {
  agents?: AgentOut[]
  heading?: string
  // When false, render only the "New chat with <agent>" control (no session list) —
  // supervisor pairs this with the grouped-by-project OpenSessions view instead.
  showList?: boolean
}) {
  const navigate = useNavigate()
  const [sessions, setSessions] = useState<ChatSession[]>([])
  const [agents, setAgents] = useState<AgentOut[]>(agentsProp ?? [])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)

  useEffect(() => {
    if (agentsProp) setAgents(agentsProp)
  }, [agentsProp])

  useEffect(() => {
    let live = true
    setLoading(true)
    const jobs: Promise<unknown>[] = []
    if (showList) jobs.push(listSessions())
    if (!agentsProp) jobs.push(listAgents({ limit: 100 }))
    Promise.allSettled(jobs).then((results) => {
      if (!live) return
      let idx = 0
      if (showList) {
        const s = results[idx++]
        if (s && s.status === 'fulfilled') setSessions(s.value as ChatSession[])
        else if (s && s.status === 'rejected')
          setError(s.reason instanceof Error ? s.reason.message : 'failed to load sessions')
      }
      const a = results[idx]
      if (!agentsProp && a && a.status === 'fulfilled') {
        setAgents((a.value as { items: AgentOut[] }).items)
      }
      setLoading(false)
    })
    return () => {
      live = false
    }
  }, [agentsProp, showList])

  const agentName = useMemo(() => {
    const by = new Map(agents.map((a) => [a.slug, a.name]))
    return (slug: string | null) => (slug ? by.get(slug) ?? slug : null)
  }, [agents])

  const startChat = useCallback(
    (agent: AgentOut) => {
      setCreating(true)
      createSession({ agentSlug: agent.slug, workspace: agent.workspace ?? undefined })
        .then((s) => navigate(`/w/${s.workspace}/chat/${s.id}`))
        .catch((err: unknown) => {
          setError(err instanceof Error ? err.message : 'could not start chat')
          setCreating(false)
        })
    },
    [navigate],
  )

  const now = new Date()

  return (
    <div className="flex min-h-0 flex-col">
      <div className="flex items-center justify-between gap-2 pb-2">
        <h2 className="text-sm font-semibold text-foreground">{heading}</h2>
        <DropdownMenu>
          <DropdownMenuTrigger render={<Button size="sm" disabled={creating || agents.length === 0} />}>
            <Plus className="mr-1 h-4 w-4" />
            New chat
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="max-h-80 overflow-y-auto">
            <DropdownMenuLabel>New chat with…</DropdownMenuLabel>
            {agents.length === 0 && <DropdownMenuItem disabled>No agents available</DropdownMenuItem>}
            {agents.map((a) => (
              <DropdownMenuItem key={`${a.workspace}/${a.slug}`} onClick={() => startChat(a)}>
                {a.name}
                {a.workspace ? <span className="ml-2 text-xs text-muted-foreground">{a.workspace}</span> : null}
              </DropdownMenuItem>
            ))}
            <DropdownMenuSeparator />
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      {showList && error && <div className="py-2 text-sm text-destructive">{error}</div>}
      {showList && (loading ? (
        <div className="py-6 text-sm text-muted-foreground">Loading sessions…</div>
      ) : sessions.length === 0 ? (
        <div className="flex flex-col items-center justify-center gap-1 py-12 text-center">
          <div className="text-sm text-foreground">No chats yet</div>
          <div className="text-xs text-muted-foreground">Start one with “New chat”.</div>
        </div>
      ) : (
        <ul className="divide-y divide-border rounded-md border border-border">
          {sessions.map((s) => {
            const who = agentName(s.agent_slug)
            return (
              <li key={s.id}>
                <Link
                  to={`/w/${s.workspace}/chat/${s.id}`}
                  className="flex items-center justify-between gap-3 px-3 py-2.5 hover:bg-muted"
                >
                  <div className="min-w-0">
                    <div className="truncate text-sm font-medium text-foreground">
                      {s.title?.trim() || 'Untitled chat'}
                    </div>
                    <div className="truncate text-xs text-muted-foreground">
                      {who ? `with ${who}` : 'no agent'} · {s.workspace}
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
      ))}
    </div>
  )
}

export default ChatSessionsPanel
