import { useEffect, useState } from 'react'
import { Link, useOutletContext } from 'react-router-dom'
import {
  listAgentSyncs,
  listAgentTasks,
  type AgentSyncOut,
  type AgentTaskOut,
  type AgentTaskStatus,
} from '@/api/agents'
import type { AgentOutletContext } from '@/pages/AgentWorkspacePage'
import { CountStat, SyncCard } from '@/components/agents/cards'
import { SectionSubHeader, SectionSkeleton } from '@/components/agents/SectionSubHeader'

const TASK_COLUMNS: { status: AgentTaskStatus; label: string; dot: string }[] = [
  { status: 'todo', label: 'To do', dot: 'bg-stone-500' },
  { status: 'in_progress', label: 'In progress', dot: 'bg-orange-400' },
  { status: 'blocked', label: 'Blocked', dot: 'bg-red-400' },
  { status: 'done', label: 'Done', dot: 'bg-emerald-400' },
]

const QUICK_LINKS: { to: string; label: string }[] = [
  { to: '../tasks', label: 'Task board' },
  { to: '../syncs', label: 'Syncs' },
  { to: '../work-products', label: 'Work products' },
  { to: '../skills', label: 'Skills' },
]

/**
 * A compact landing dashboard for an agent — NOT the full lists. Persona +
 * description, a counts row, the single latest sync, a condensed task summary
 * (counts per board column), and quick links into the deeper sections.
 */
export function AgentOverviewSection() {
  const { agent } = useOutletContext<AgentOutletContext>()
  const [latestSync, setLatestSync] = useState<AgentSyncOut | null>(null)
  const [tasks, setTasks] = useState<AgentTaskOut[] | null>(null)

  useEffect(() => {
    let cancelled = false
    setLatestSync(null)
    setTasks(null)
    void Promise.all([
      listAgentSyncs(agent.slug, { limit: 1 }),
      listAgentTasks(agent.slug),
    ])
      .then(([syncPage, taskList]) => {
        if (cancelled) return
        setLatestSync(syncPage.items[0] ?? null)
        setTasks(taskList)
      })
      .catch(() => {
        if (cancelled) return
        setLatestSync(null)
        setTasks([])
      })
    return () => {
      cancelled = true
    }
  }, [agent.slug])

  const tasksLoading = tasks === null
  const countFor = (status: AgentTaskStatus) =>
    (tasks ?? []).filter((t) => t.status === status).length

  return (
    <div className="max-w-4xl px-6 py-8">
      <SectionSubHeader title="Overview" />

      {/* Persona / description */}
      {(agent.persona || agent.description) && (
        <div className="mb-6">
          {agent.persona && (
            <p className="text-[14px] text-stone-300 leading-relaxed">{agent.persona}</p>
          )}
          {agent.description && (
            <p className="text-[13px] text-stone-400 leading-relaxed mt-2">{agent.description}</p>
          )}
        </div>
      )}

      {/* Counts row */}
      <div className="flex flex-wrap gap-6 pb-6 mb-6 border-b border-stone-800">
        <CountStat value={agent.task_count} label="Tasks" />
        <CountStat value={agent.sync_count} label="Syncs" />
        <CountStat value={agent.work_product_count} label="Work" />
        <CountStat value={agent.skill_count} label="Skills" />
      </div>

      {/* Task summary — counts per board column */}
      <div className="mb-8">
        <div className="flex items-baseline justify-between mb-3">
          <h2 className="text-[11px] font-bold uppercase tracking-[0.08em] text-orange-300">
            Tasks
          </h2>
          <Link
            to="../tasks"
            className="text-[11px] text-stone-500 hover:text-orange-400 transition-colors"
          >
            Open board →
          </Link>
        </div>
        {tasksLoading ? (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {TASK_COLUMNS.map((c) => (
              <div key={c.status} className="h-16 rounded-lg bg-stone-900 border border-stone-800 animate-pulse" />
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {TASK_COLUMNS.map((c) => (
              <div
                key={c.status}
                className="rounded-lg bg-stone-900/70 border border-stone-800 px-3 py-3"
              >
                <div className="flex items-center gap-2">
                  <span className={`h-1.5 w-1.5 rounded-full ${c.dot}`} />
                  <span className="text-[10px] font-semibold uppercase tracking-[0.06em] text-stone-400">
                    {c.label}
                  </span>
                </div>
                <span className="block text-lg font-semibold text-stone-100 leading-none mt-2">
                  {countFor(c.status)}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Latest sync */}
      <div className="mb-8">
        <div className="flex items-baseline justify-between mb-3">
          <h2 className="text-[11px] font-bold uppercase tracking-[0.08em] text-orange-300">
            Latest sync
          </h2>
          <Link
            to="../syncs"
            className="text-[11px] text-stone-500 hover:text-orange-400 transition-colors"
          >
            All syncs →
          </Link>
        </div>
        {latestSync === null && tasksLoading ? (
          <SectionSkeleton rows={1} />
        ) : latestSync ? (
          <SyncCard sync={latestSync} />
        ) : (
          <p className="text-[13px] text-stone-600">No syncs yet.</p>
        )}
      </div>

      {/* Quick links */}
      <div className="flex flex-wrap gap-2">
        {QUICK_LINKS.map((l) => (
          <Link
            key={l.to}
            to={l.to}
            className="inline-flex items-center gap-1 text-[12px] font-medium text-stone-300 hover:text-orange-300 bg-stone-900/70 border border-stone-800 hover:border-orange-400/40 px-3 py-1.5 rounded-md transition-colors"
          >
            {l.label}
            <span className="text-orange-400/70">→</span>
          </Link>
        ))}
      </div>
    </div>
  )
}
