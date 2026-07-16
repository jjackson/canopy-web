import { useEffect, useState, type JSX } from 'react'
import { listAgentSkills, type AgentOut, type AgentSkillOut } from '@/api/agents'
import { enqueueTurn } from '@/api/harness'
import { listWorkspaces, type WorkspaceOut } from '@/api/workspaces'
import { useAuth } from '@/auth/AuthProvider'
import { buildDispatchPrompt, canDispatch, phoneThreadKey } from '@/lib/dispatchPrompt'

// The phone composer: dispatch a turn without opening a laptop. Two targets.
//
// AGENT — pick an agent → a LAUNCHABLE skill (the agent declares which of its
// catalog are human entry points; #232) or a free prompt. Routes through the
// flat mount; the server derives the agent's workspace.
//
// REPO — pick a repo (e.g. canopy-web) → a free prompt (repos have no skill
// catalog). A repo turn is OWNED BY A WORKSPACE, first-class: the composer picks
// it (defaulting to dimagi) and pins it explicitly, so the turn lands in the
// right tenant even though /supervisor is not itself a tenant surface.

// dimagi is the default repo tenant for now (Jonathan, 2026-07-16) — a value the
// composer defaults to, NOT a server fallback, so repo→workspace ownership stays
// explicit and survives into cloud/multiplayer mode.
const DEFAULT_REPO_WORKSPACE = 'dimagi'

type Sent = { kind: 'ok'; label: string } | { kind: 'err'; message: string }
type Mode = 'agent' | 'repo'

export function Composer({ agents }: { agents: AgentOut[] }): JSX.Element {
  const { user } = useAuth()
  const [mode, setMode] = useState<Mode>('agent')

  // Agent mode
  const [slug, setSlug] = useState<string>(agents[0]?.slug ?? '')
  const [skills, setSkills] = useState<AgentSkillOut[] | null>(null)
  const [skillName, setSkillName] = useState<string>('') // '' = free prompt

  // Repo mode
  const [project, setProject] = useState('')
  const [workspaces, setWorkspaces] = useState<WorkspaceOut[]>([])
  const [workspace, setWorkspace] = useState<string>(DEFAULT_REPO_WORKSPACE)

  const [args, setArgs] = useState('')
  const [busy, setBusy] = useState(false)
  const [sent, setSent] = useState<Sent | null>(null)

  // Load the selected agent's launchable skills. A non-launchable skill is a
  // footgun on a phone (/echo:setup one thumb away), so the catalog is filtered
  // to launchable here — the server marks them, we never render the rest.
  useEffect(() => {
    if (mode !== 'agent' || !slug) return
    let cancelled = false
    setSkills(null)
    setSkillName('')
    listAgentSkills(slug)
      .then((all) => {
        if (!cancelled) setSkills(all.filter((s) => s.launchable))
      })
      .catch(() => {
        if (!cancelled) setSkills([])
      })
  }, [slug, mode])

  // The user's workspaces populate the repo tenant selector — first-class
  // ownership, defaulting to dimagi when present.
  useEffect(() => {
    let cancelled = false
    listWorkspaces()
      .then((ws) => {
        if (cancelled) return
        setWorkspaces(ws)
        if (!ws.some((w) => w.slug === DEFAULT_REPO_WORKSPACE) && ws[0]) {
          setWorkspace(ws[0].slug)
        }
      })
      .catch(() => {
        /* leave the default; a repo dispatch will surface any error inline */
      })
  }, [])

  const selected = skills?.find((s) => s.name === skillName)
  const prompt =
    mode === 'agent' ? buildDispatchPrompt(slug, skillName, args) : args.trim()
  const target = mode === 'agent' ? slug : project.trim()
  const canSend = !busy && canDispatch(target, prompt) && (mode === 'agent' || workspace !== '')

  async function send(): Promise<void> {
    if (!canSend) return
    setBusy(true)
    setSent(null)
    try {
      if (mode === 'agent') {
        await enqueueTurn({ agentSlug: slug, prompt })
        setSent({ kind: 'ok', label: skillName ? `/${slug}:${skillName}` : slug })
      } else {
        // A stable per-(user,repo) thread so successive dispatches CONTINUE one
        // session — the phone drives a persistent canopy-web thread rather than
        // spawning a fresh emdash task per message.
        const threadKey = user ? phoneThreadKey(user.email, target) : undefined
        await enqueueTurn({ project: target, workspace, prompt, threadKey })
        setSent({ kind: 'ok', label: `${target} · ${workspace}` })
      }
      setArgs('')
      setSkillName('')
    } catch (e) {
      setSent({ kind: 'err', message: e instanceof Error ? e.message : 'Failed to send' })
    } finally {
      setBusy(false)
    }
  }

  if (agents.length === 0) return <></>

  return (
    <div className="flex flex-col gap-2 rounded-lg border border-border bg-card p-3" data-testid="composer">
      {/* Target-type toggle */}
      <div className="flex gap-1 self-start rounded-md border border-input p-0.5 text-[12px]">
        {(['agent', 'repo'] as Mode[]).map((m) => (
          <button
            key={m}
            type="button"
            data-testid={`composer-mode-${m}`}
            onClick={() => {
              setMode(m)
              setSent(null)
              setArgs('')
            }}
            className={
              mode === m
                ? 'rounded bg-primary px-2.5 py-1 font-medium text-primary-foreground'
                : 'rounded px-2.5 py-1 text-muted-foreground hover:text-foreground'
            }
          >
            {m === 'agent' ? 'Agent' : 'Repo'}
          </button>
        ))}
      </div>

      {mode === 'agent' ? (
        <div className="flex flex-wrap gap-2">
          <label className="sr-only" htmlFor="composer-agent">
            Agent
          </label>
          <select
            id="composer-agent"
            data-testid="composer-agent"
            value={slug}
            onChange={(e) => setSlug(e.target.value)}
            className="rounded border border-input bg-input px-2 py-1.5 text-[13px] text-foreground"
          >
            {agents.map((a) => (
              <option key={a.slug} value={a.slug}>
                {a.name}
              </option>
            ))}
          </select>

          <label className="sr-only" htmlFor="composer-skill">
            Command
          </label>
          <select
            id="composer-skill"
            data-testid="composer-skill"
            value={skillName}
            onChange={(e) => setSkillName(e.target.value)}
            disabled={skills === null}
            className="min-w-0 flex-1 rounded border border-input bg-input px-2 py-1.5 text-[13px] text-foreground disabled:opacity-50"
          >
            <option value="">Free prompt…</option>
            {(skills ?? []).map((s) => (
              <option key={s.name} value={s.name}>
                /{slug}:{s.name}
              </option>
            ))}
          </select>
        </div>
      ) : (
        <div className="flex flex-wrap gap-2">
          <label className="sr-only" htmlFor="composer-project">
            Repo
          </label>
          <input
            id="composer-project"
            data-testid="composer-project"
            value={project}
            onChange={(e) => setProject(e.target.value)}
            placeholder="repo (e.g. canopy-web)"
            className="min-w-0 flex-1 rounded border border-input bg-input px-2 py-1.5 text-[13px] text-foreground placeholder:text-muted-foreground"
          />
          <label className="sr-only" htmlFor="composer-workspace">
            Workspace
          </label>
          <select
            id="composer-workspace"
            data-testid="composer-workspace"
            value={workspace}
            onChange={(e) => setWorkspace(e.target.value)}
            title="Which workspace owns this repo turn"
            className="rounded border border-input bg-input px-2 py-1.5 text-[13px] text-foreground"
          >
            {/* Keep the default selectable even before the list loads. */}
            {workspaces.length === 0 ? (
              <option value={DEFAULT_REPO_WORKSPACE}>{DEFAULT_REPO_WORKSPACE}</option>
            ) : (
              workspaces.map((w) => (
                <option key={w.slug} value={w.slug}>
                  {w.slug}
                </option>
              ))
            )}
          </select>
        </div>
      )}

      <div className="flex gap-2">
        <input
          data-testid="composer-args"
          value={args}
          onChange={(e) => setArgs(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') void send()
          }}
          placeholder={
            mode === 'repo'
              ? 'What should the agent do in this repo?'
              : selected?.args_hint || (skillName ? 'arguments (optional)' : 'Type a prompt…')
          }
          className="min-w-0 flex-1 rounded border border-input bg-input px-2 py-1.5 text-[13px] text-foreground placeholder:text-muted-foreground"
        />
        <button
          type="button"
          data-testid="composer-send"
          onClick={() => void send()}
          disabled={!canSend}
          className="rounded bg-primary px-3 py-1.5 text-[13px] font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
        >
          {busy ? 'Sending…' : 'Send'}
        </button>
      </div>

      {/* The exact command about to fire (agent mode) — no surprise about what lands. */}
      {mode === 'agent' && prompt.trim() !== '' && (
        <p className="truncate font-mono text-[11px] text-muted-foreground" data-testid="composer-preview">
          {prompt}
        </p>
      )}

      {sent?.kind === 'ok' && (
        <p className="text-[12px] text-success" data-testid="composer-sent">
          Queued {sent.label} — the runner picks it up on its next tick.
        </p>
      )}
      {sent?.kind === 'err' && (
        <p className="text-[12px] text-destructive" data-testid="composer-error">
          {sent.message}
        </p>
      )}
    </div>
  )
}
