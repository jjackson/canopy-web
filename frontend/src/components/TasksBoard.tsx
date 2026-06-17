import type { AgentTaskOut, AgentTaskStatus } from '@/api/agents'

const COLUMNS: { status: AgentTaskStatus; label: string }[] = [
  { status: 'todo', label: 'To do' },
  { status: 'in_progress', label: 'In progress' },
  { status: 'blocked', label: 'Blocked' },
  { status: 'done', label: 'Done' },
]

// A small dot per column so the board reads at a glance.
const COLUMN_DOT: Record<AgentTaskStatus, string> = {
  todo: 'bg-stone-500',
  in_progress: 'bg-orange-400',
  blocked: 'bg-red-400',
  done: 'bg-emerald-400',
}

function formatDue(s: string): string {
  return new Date(s).toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
  })
}

function isPastDue(due: string): boolean {
  const d = new Date(due)
  if (Number.isNaN(d.getTime())) return false
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  return d.getTime() < today.getTime()
}

// high → red/amber, medium → neutral, low → muted, anything else → muted/quiet.
function priorityChipClass(priority: string): string {
  switch ((priority || '').trim().toLowerCase()) {
    case 'high':
    case 'urgent':
    case 'critical':
      return 'text-red-300 bg-red-950/50 border-red-500/40'
    case 'medium':
    case 'normal':
      return 'text-stone-300 bg-stone-800 border-stone-700/60'
    case 'low':
      return 'text-stone-500 bg-stone-950/60 border-stone-800'
    default:
      return 'text-stone-500 bg-stone-950/60 border-stone-800'
  }
}

function PriorityChip({ priority }: { priority: string }) {
  const label = (priority || '').trim()
  if (!label) return null
  return (
    <span
      className={`inline-flex items-center text-[10px] font-semibold uppercase tracking-wide px-1.5 py-0.5 rounded border ${priorityChipClass(
        priority,
      )}`}
    >
      {label}
    </span>
  )
}

function TaskLinkChip({ label, url }: { label: string; url: string }) {
  if (!url) return null
  return (
    <a
      href={url}
      target="_blank"
      rel="noreferrer"
      className="inline-flex items-center gap-1 text-[10px] font-medium text-stone-300 hover:text-orange-300 bg-stone-950/80 border border-stone-700/60 hover:border-orange-400/50 px-2 py-0.5 rounded transition-colors"
    >
      <span className="text-orange-400/70">↗</span>
      {label || url}
    </a>
  )
}

function TaskCard({ task }: { task: AgentTaskOut }) {
  const pastDue = task.due ? task.status !== 'done' && isPastDue(task.due) : false
  return (
    <div className="bg-stone-900/70 border border-stone-800 rounded-lg p-3 hover:border-orange-400/40 transition-colors">
      <p className="text-[13px] font-semibold text-stone-100 leading-snug">{task.title}</p>

      <div className="flex flex-wrap items-center gap-1.5 mt-2">
        <PriorityChip priority={task.priority} />
        {task.owner && (
          <span className="inline-flex items-center text-[10px] text-stone-400 bg-stone-950/60 border border-stone-800 px-1.5 py-0.5 rounded">
            {task.owner}
          </span>
        )}
        {task.due && (
          <span
            className={`inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded border ${
              pastDue
                ? 'text-red-300 bg-red-950/40 border-red-500/40'
                : 'text-stone-500 bg-stone-950/60 border-stone-800'
            }`}
            title={pastDue ? 'Past due' : undefined}
          >
            {pastDue && <span aria-hidden>⚠</span>}
            {formatDue(task.due)}
          </span>
        )}
      </div>

      {task.links && task.links.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mt-2">
          {task.links.map((l, i) => (
            <TaskLinkChip key={`${l.url}-${i}`} label={l.label} url={l.url} />
          ))}
        </div>
      )}
    </div>
  )
}

export function TasksBoard({ tasks }: { tasks: AgentTaskOut[] }) {
  const byStatus = (status: AgentTaskStatus) =>
    tasks
      .filter((t) => t.status === status)
      .sort((a, b) => a.position - b.position)

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
      {COLUMNS.map(({ status, label }) => {
        const items = byStatus(status)
        return (
          <div key={status} className="flex flex-col min-w-0">
            <div className="flex items-center gap-2 px-1 pb-2 mb-2 border-b border-stone-800">
              <span className={`h-1.5 w-1.5 rounded-full ${COLUMN_DOT[status]}`} />
              <span className="text-[11px] font-bold uppercase tracking-[0.06em] text-stone-300">
                {label}
              </span>
              <span className="text-[11px] text-stone-600 ml-auto">{items.length}</span>
            </div>
            {items.length === 0 ? (
              <p className="text-[11px] text-stone-600 italic px-1 py-3">No tasks</p>
            ) : (
              <div className="space-y-2">
                {items.map((t) => (
                  <TaskCard key={t.id} task={t} />
                ))}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}
