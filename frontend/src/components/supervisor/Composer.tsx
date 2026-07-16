import { useEffect, useState, type JSX } from 'react'
import { listAgentSkills, type AgentOut, type AgentSkillOut } from '@/api/agents'
import { enqueueTurn } from '@/api/harness'
import { buildDispatchPrompt, canDispatch } from '@/lib/dispatchPrompt'

// The phone composer: dispatch a command to an agent without opening a laptop.
// Pick an agent → pick one of its LAUNCHABLE skills (the agent declares which of
// its catalog are human entry points; see AgentSkill.launchable) or type a free
// prompt → send. The dispatch enqueues a manual turn the runner claims within a
// poll tick; the prompt is exactly the namespaced command, which the agent's
// /<slug>:<skill> does all the work from.
//
// Repo (project) dispatch is intentionally absent — see enqueueTurn's note.

type Sent = { kind: 'ok'; label: string } | { kind: 'err'; message: string }

export function Composer({ agents }: { agents: AgentOut[] }): JSX.Element {
  const [slug, setSlug] = useState<string>(agents[0]?.slug ?? '')
  const [skills, setSkills] = useState<AgentSkillOut[] | null>(null)
  const [skillName, setSkillName] = useState<string>('') // '' = free prompt
  const [args, setArgs] = useState('')
  const [busy, setBusy] = useState(false)
  const [sent, setSent] = useState<Sent | null>(null)

  // Load the selected agent's launchable skills. A non-launchable skill is a
  // footgun on a phone (/echo:setup one thumb away), so the catalog is filtered
  // to launchable here — the server marks them, we never render the rest.
  useEffect(() => {
    if (!slug) return
    let cancelled = false
    setSkills(null)
    setSkillName('')
    setArgs('')
    listAgentSkills(slug)
      .then((all) => {
        if (!cancelled) setSkills(all.filter((s) => s.launchable))
      })
      .catch(() => {
        if (!cancelled) setSkills([])
      })
  }, [slug])

  const selected = skills?.find((s) => s.name === skillName)
  const prompt = buildDispatchPrompt(slug, skillName, args)
  const canSend = !busy && canDispatch(slug, prompt)

  async function send(): Promise<void> {
    if (!canSend) return
    setBusy(true)
    setSent(null)
    try {
      await enqueueTurn({ agentSlug: slug, prompt: prompt.trim() })
      setSent({ kind: 'ok', label: skillName ? `/${slug}:${skillName}` : slug })
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

      <div className="flex gap-2">
        <input
          data-testid="composer-args"
          value={args}
          onChange={(e) => setArgs(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') void send()
          }}
          placeholder={selected?.args_hint || (skillName ? 'arguments (optional)' : 'Type a prompt…')}
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

      {/* The exact command about to fire — no surprise about what lands in the session. */}
      {prompt.trim() !== '' && (
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
