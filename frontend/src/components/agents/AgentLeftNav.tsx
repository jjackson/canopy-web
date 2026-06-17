import { Link, NavLink } from 'react-router-dom'
import { clsx } from 'clsx'
import type { AgentDetailOut } from '@/api/agents'

/**
 * The persistent left rail for the Agent Workspace. Mirrors DddLeftNav's shell
 * (a bordered aside with a top identity block + a vertical section nav). Each
 * section links to its own sub-route under /agents/:slug and carries a
 * right-aligned count badge sourced from the agent detail.
 */
type NavItem = {
  to: string
  label: string
  count?: number
}

export function AgentLeftNav({ agent }: { agent: AgentDetailOut }) {
  const items: NavItem[] = [
    { to: 'overview', label: 'Overview' },
    { to: 'tasks', label: 'Tasks', count: agent.task_count },
    { to: 'syncs', label: 'Syncs', count: agent.sync_count },
    { to: 'work-products', label: 'Work products', count: agent.work_product_count },
    { to: 'skills', label: 'Skills', count: agent.skill_count },
  ]

  return (
    <aside className="flex w-64 shrink-0 flex-col border-r border-stone-800 bg-stone-950/40">
      <div className="border-b border-stone-800 px-4 py-4">
        <Link
          to="/agents"
          className="text-[12px] text-stone-500 hover:text-orange-400 transition-colors"
        >
          ← Agents
        </Link>
        <div className="flex items-start gap-3 mt-3">
          {agent.avatar_url ? (
            <img
              src={agent.avatar_url}
              alt=""
              className="h-10 w-10 rounded-full shrink-0 object-cover border border-stone-800"
            />
          ) : (
            <span className="h-10 w-10 rounded-full shrink-0 bg-orange-500/90 text-white text-sm font-semibold flex items-center justify-center">
              {(agent.name || agent.slug).slice(0, 1).toUpperCase()}
            </span>
          )}
          <div className="min-w-0">
            <h2 className="text-sm font-semibold text-stone-100 leading-snug truncate">
              {agent.name}
            </h2>
            {agent.email && (
              <a
                href={`mailto:${agent.email}`}
                className="block text-[11px] text-stone-500 hover:text-orange-400 transition-colors truncate"
              >
                {agent.email}
              </a>
            )}
          </div>
        </div>
      </div>

      <nav className="flex-1 overflow-y-auto px-2 py-3">
        <div className="flex flex-col gap-0.5">
          {items.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                clsx(
                  'flex items-center justify-between gap-2 rounded-md px-3 py-1.5 text-sm transition-colors',
                  isActive
                    ? 'bg-orange-400/10 border border-orange-400/30 text-orange-400 font-medium'
                    : 'border border-transparent text-stone-400 hover:bg-stone-800/40 hover:text-stone-200',
                )
              }
            >
              <span className="truncate">{item.label}</span>
              {item.count !== undefined && (
                <span className="shrink-0 text-[11px] text-stone-500">{item.count}</span>
              )}
            </NavLink>
          ))}
        </div>
      </nav>
    </aside>
  )
}
