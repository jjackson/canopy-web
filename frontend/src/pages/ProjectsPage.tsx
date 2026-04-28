import { useEffect, useState } from 'react'
import { AnimatePresence, LayoutGroup, motion } from 'framer-motion'
import { type Project, projectsApi } from '@/api/projects'

const SPRING = { type: 'spring' as const, stiffness: 400, damping: 35 }

// Curated hygiene checklist rendered in the expanded card's "Actions" column.
// `key` MUST match the exact `skill_name` written via POST /api/projects/{slug}/actions/
// (canopy skills are namespaced with `canopy:`; other writers use bare names).
// `label` is what the user sees — keep it clean and prefix-free.
// Update this list as new hygiene skills are added to the portfolio workflow.
const HYGIENE_ACTIONS: Array<{ key: string; label: string }> = [
  { key: 'code-review', label: 'code-review' },
  { key: 'canopy:doc-regen', label: 'doc-regen' },
  { key: 'canopy:improve', label: 'improve' },
  { key: 'canopy:pm-scout', label: 'pm-scout' },
]

function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime()
  const minutes = Math.floor(diff / 60000)
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  if (days < 7) return `${days}d ago`
  return new Date(iso).toLocaleDateString()
}

function StatusDot({ status }: { status: string }) {
  const color = status === 'active'
    ? 'bg-orange-400 shadow-[0_0_6px_rgba(251,146,60,0.3)]'
    : status === 'stale'
      ? 'bg-stone-500'
      : 'bg-stone-700'
  return <span className={`w-[7px] h-[7px] rounded-full shrink-0 ${color}`} />
}

function DeployBadge({ url, compact }: { url: string; compact?: boolean }) {
  if (!url) return null
  const hostname = (() => {
    try { return new URL(url).hostname.replace('www.', '') } catch { return url }
  })()
  return (
    <a href={url} target="_blank" rel="noopener noreferrer"
      title={hostname}
      className={`flex items-center gap-1.5 min-w-0 ${compact ? 'text-[10px] max-w-[110px]' : 'text-[11px] max-w-[240px]'} bg-stone-800 text-stone-400 px-2 py-0.5 rounded hover:text-stone-200 transition-colors overflow-hidden`}
      onClick={(e) => e.stopPropagation()}>
      <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 shrink-0 animate-pulse-slow shadow-[0_0_4px_rgba(74,222,128,0.4)]" />
      <span className="truncate">{hostname}</span>
    </a>
  )
}

function PrivateBadge() {
  return (
    <span className="text-[9px] text-stone-500 border border-orange-400/15 bg-orange-400/5 px-1.5 py-0.5 rounded uppercase tracking-wide">
      private
    </span>
  )
}

function CollapsedTile({ project, onExpand }: { project: Project; onExpand: () => void }) {
  const ctx = project.latest_context || {}
  const summaryText = ctx.summary?.content || ctx.current_work?.content
  const summaryDate = ctx.summary?.created_at
  const isStale = summaryDate
    ? (Date.now() - new Date(summaryDate).getTime()) / (1000 * 60 * 60 * 24) > 7
    : false
  const borderClass = isStale
    ? 'border border-l-2 border-stone-800 border-l-amber-400/30 hover:border-stone-700 hover:border-l-amber-400/50'
    : 'border border-stone-800 hover:border-stone-700'
  return (
    <div
      className={`bg-stone-900 ${borderClass} rounded-lg p-4 cursor-pointer transition-colors h-full`}
      onClick={onExpand}
    >
      <div className="flex items-center gap-3 mb-2 min-w-0">
        <StatusDot status={project.status} />
        <span className="text-sm font-semibold text-stone-100 truncate min-w-0">{project.name}</span>
        <div className="ml-auto flex items-center gap-2 min-w-0 shrink">
          {project.visibility === 'private' && <PrivateBadge />}
          {project.deploy_url && <DeployBadge url={project.deploy_url} compact />}
        </div>
      </div>
      <div className="text-xs text-stone-500 leading-relaxed line-clamp-2">
        {summaryText || <span className="text-stone-700 italic">No summary yet</span>}
      </div>
    </div>
  )
}

function ExpandedCard({ project, onClose }: {
  project: Project
  onClose: () => void
}) {
  const [skillsExpanded, setSkillsExpanded] = useState(false)
  const ctx = project.latest_context || {}
  const skills = project.skills || []

  return (
    <div
      className="bg-stone-900 border border-stone-700 rounded-xl overflow-hidden"
      onClick={(e) => e.stopPropagation()}
    >
      {/* Header */}
      <div className="flex items-center gap-3 px-6 py-4 border-b border-stone-800">
        <StatusDot status={project.status} />
        <span className="text-base font-bold text-stone-100">{project.name}</span>
        {project.visibility === 'private' && <PrivateBadge />}
        {project.deploy_url && <DeployBadge url={project.deploy_url} />}
        <div className="ml-auto flex items-center gap-4 text-[11px]">
          {project.repo_url && (
            <a href={project.repo_url} target="_blank" rel="noopener noreferrer"
              className="text-orange-400/70 hover:text-orange-400 transition-colors"
              onClick={(e) => e.stopPropagation()}>
              GitHub ↗
            </a>
          )}
          {project.deploy_url && (
            <a href={project.deploy_url} target="_blank" rel="noopener noreferrer"
              className="text-orange-400/70 hover:text-orange-400 transition-colors"
              onClick={(e) => e.stopPropagation()}>
              Live Site ↗
            </a>
          )}
        </div>
        <button
          onClick={(e) => { e.stopPropagation(); onClose() }}
          className="text-stone-700 hover:text-stone-400 text-lg ml-2"
          aria-label="Close"
        >✕</button>
      </div>

      {/* Body — 3 columns */}
      <div className="grid grid-cols-1 md:grid-cols-3 divide-x divide-stone-800">
        {/* Column 1: Summary */}
        <div className="p-6">
          <div className="text-[9px] uppercase tracking-wider text-stone-600 font-semibold mb-4">Summary</div>
          {ctx.summary ? (
            <div>
              <div className="bg-stone-950 border-l-2 border-orange-400 rounded-r-lg p-3 text-xs text-stone-400 leading-relaxed">
                {ctx.summary.content}
              </div>
              <div className="text-[10px] text-stone-700 mt-2">
                {ctx.summary.source} · {new Date(ctx.summary.created_at).toLocaleDateString()}
              </div>
            </div>
          ) : (
            <div className="text-xs text-stone-700 italic">No summary yet — run canopy:activity-summary</div>
          )}
        </div>

        {/* Column 2: Actions */}
        <div className="p-6">
          <div className="text-[9px] uppercase tracking-wider text-stone-600 font-semibold mb-4">Actions</div>
          {(() => {
            const actions = project.latest_actions || {}
            return (
              <div className="space-y-2">
                {HYGIENE_ACTIONS.map(({ key, label }) => {
                  const action = actions[key]
                  return (
                    <div key={key} className="flex items-center justify-between text-[11px]">
                      <span className="text-stone-400">{label}</span>
                      {action ? (
                        <div className="flex items-center gap-2">
                          <span className="text-stone-600">{relativeTime(action.completed_at || action.started_at)}</span>
                          {action.status === 'completed' && <span className="text-emerald-400">&#10003;</span>}
                          {action.status === 'failed' && <span className="text-red-400">&#10007;</span>}
                          {action.status === 'started' && <span className="text-orange-400">&#9679;</span>}
                        </div>
                      ) : (
                        <span className="text-stone-800">never</span>
                      )}
                    </div>
                  )
                })}
              </div>
            )
          })()}
        </div>

        {/* Column 3: Details + Skills */}
        <div className="p-6">
          <div className="text-[9px] uppercase tracking-wider text-stone-600 font-semibold mb-4">Details</div>
          <div className="space-y-2 mb-6">
            <div className="flex items-center justify-between text-xs">
              <span className="text-stone-600">Repo</span>
              {project.repo_url ? (
                <a href={project.repo_url} target="_blank" rel="noopener noreferrer"
                  className="text-orange-400/80 hover:text-orange-400 truncate ml-3 max-w-[180px]"
                  onClick={(e) => e.stopPropagation()}>
                  {project.repo_url.replace('https://github.com/', '')}
                </a>
              ) : <span className="text-stone-700">—</span>}
            </div>
            <div className="flex items-center justify-between text-xs">
              <span className="text-stone-600">Deploy</span>
              {project.deploy_url ? (
                <a href={project.deploy_url} target="_blank" rel="noopener noreferrer"
                  className="text-orange-400/80 hover:text-orange-400 truncate ml-3 max-w-[180px]"
                  onClick={(e) => e.stopPropagation()}>
                  {(() => { try { return new URL(project.deploy_url).hostname } catch { return project.deploy_url } })()}
                </a>
              ) : <span className="text-stone-700">—</span>}
            </div>
            <div className="flex items-center justify-between text-xs">
              <span className="text-stone-600">Visibility</span>
              <span className="text-stone-300">{project.visibility}</span>
            </div>
          </div>

          {/* Last actions */}
          {project.latest_actions && Object.keys(project.latest_actions).length > 0 && (
            <div className="mb-6">
              <div className="text-[9px] uppercase tracking-wider text-stone-600 font-semibold mb-2">Last actions</div>
              <div className="space-y-1">
                {Object.entries(project.latest_actions).map(([name, action]) => (
                  <div key={name} className="flex items-center justify-between text-[11px]">
                    <span className="text-stone-400 truncate mr-2">{name}</span>
                    <div className="flex items-center gap-2 shrink-0">
                      <span className="text-stone-600">{relativeTime(action.completed_at || action.started_at)}</span>
                      {action.status === 'completed' && <span className="text-emerald-400">&#10003;</span>}
                      {action.status === 'failed' && <span className="text-red-400">&#10007;</span>}
                      {action.status === 'started' && <span className="text-orange-400">&#9679;</span>}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Skills (collapsible) */}
          <div>
            <button
              onClick={(e) => { e.stopPropagation(); setSkillsExpanded(!skillsExpanded) }}
              className="flex items-center gap-2 text-[9px] uppercase tracking-wider text-stone-600 font-semibold mb-2 hover:text-stone-400 transition-colors">
              <span>Skills ({skills.length})</span>
              <span>{skillsExpanded ? '▾' : '▸'}</span>
            </button>
            {skillsExpanded && (
              <div className="space-y-1">
                {skills.length === 0 ? (
                  <div className="text-[11px] text-stone-700 italic">No skills discovered</div>
                ) : (
                  skills.map((skill, i) => (
                    <div key={i} className="text-[11px] text-stone-400 py-1">
                      <div className="font-medium text-stone-300">{skill.name}</div>
                      {skill.description && (
                        <div className="text-stone-600 text-[10px] line-clamp-2">{skill.description}</div>
                      )}
                    </div>
                  ))
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

function LoadingSkeleton() {
  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-lg font-semibold text-stone-100">Projects</h1>
        <span className="text-xs text-stone-700 bg-stone-900 px-2.5 py-1 rounded">
          loading…
        </span>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-2">
        {Array.from({ length: 8 }).map((_, i) => (
          <div
            key={i}
            className="bg-stone-900 border border-stone-800 rounded-lg p-4 animate-pulse"
            style={{ animationDelay: `${i * 60}ms` }}
          >
            <div className="flex items-center gap-3 mb-3">
              <div className="w-[7px] h-[7px] rounded-full bg-stone-800 shrink-0" />
              <div className="h-3 bg-stone-800 rounded w-1/2" />
            </div>
            <div className="space-y-2">
              <div className="h-2 bg-stone-800/70 rounded w-full" />
              <div className="h-2 bg-stone-800/70 rounded w-4/5" />
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

export function ProjectsPage() {
  const [projects, setProjects] = useState<Project[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  // Ordered list of slugs that are expanded; first = most-recently clicked (top of stack).
  const [expandedOrder, setExpandedOrder] = useState<string[]>([])

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    void (async () => {
      try {
        const data = await projectsApi.list()
        if (!cancelled) setProjects(data)
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Failed to load projects')
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => { cancelled = true }
  }, [])

  function expand(slug: string) {
    setExpandedOrder((order) => (order.includes(slug) ? order : [slug, ...order]))
  }

  function collapse(slug: string) {
    setExpandedOrder((order) => order.filter((s) => s !== slug))
  }

  if (loading) {
    return <LoadingSkeleton />
  }
  if (error) {
    return <div className="flex items-center justify-center h-64 text-red-400 text-sm">{error}</div>
  }

  const expandedSet = new Set(expandedOrder)
  const expandedProjects = expandedOrder
    .map((slug) => projects.find((p) => p.slug === slug))
    .filter((p): p is Project => Boolean(p))
  const collapsedProjects = projects.filter((p) => !expandedSet.has(p.slug))

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-lg font-semibold text-stone-100">Projects</h1>
        <span className="text-xs text-stone-600 bg-stone-900 px-2.5 py-1 rounded">
          {projects.length} projects
        </span>
      </div>

      <LayoutGroup>
        {/* Stack of expanded cards at the top */}
        <div className="space-y-3 mb-3">
          <AnimatePresence initial={false}>
            {expandedProjects.map((project) => (
              <motion.div
                key={project.id}
                layout
                initial={{ opacity: 0, y: -8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -8 }}
                transition={SPRING}
              >
                <ExpandedCard
                  project={project}
                  onClose={() => collapse(project.slug)}
                />
              </motion.div>
            ))}
          </AnimatePresence>
        </div>

        {/* Collapsed tile grid */}
        <motion.div
          layout
          className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-2"
          transition={SPRING}
        >
          <AnimatePresence initial={false}>
            {collapsedProjects.map((project, i) => (
              <motion.div
                key={project.id}
                layout
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: 8 }}
                transition={{ ...SPRING, delay: Math.min(i * 0.03, 0.3), duration: 0.2 }}
              >
                <CollapsedTile project={project} onExpand={() => expand(project.slug)} />
              </motion.div>
            ))}
          </AnimatePresence>
        </motion.div>
      </LayoutGroup>
    </div>
  )
}
