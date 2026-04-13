import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { AnimatePresence, LayoutGroup, motion } from 'framer-motion'
import { type Project, projectsApi } from '@/api/projects'

const SPRING = { type: 'spring' as const, stiffness: 400, damping: 35 }

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
      className={`inline-flex items-center gap-1.5 ${compact ? 'text-[10px]' : 'text-[11px]'} bg-stone-800 text-stone-400 px-2 py-0.5 rounded hover:text-stone-200 transition-colors max-w-[240px] overflow-hidden`}
      onClick={(e) => e.stopPropagation()}>
      <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 shadow-[0_0_4px_rgba(74,222,128,0.4)] shrink-0" />
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
  const currentWork = ctx.current_work?.content
  return (
    <div
      className="bg-stone-900 border border-stone-800 hover:border-stone-700 rounded-lg p-4 cursor-pointer transition-colors h-full"
      onClick={onExpand}
    >
      <div className="flex items-center gap-3 mb-2">
        <StatusDot status={project.status} />
        <span className="text-sm font-semibold text-stone-100">{project.name}</span>
        <div className="ml-auto flex items-center gap-2">
          {project.visibility === 'private' && <PrivateBadge />}
          {project.deploy_url && <DeployBadge url={project.deploy_url} compact />}
        </div>
      </div>
      <div className="text-xs text-stone-500 leading-relaxed line-clamp-2">
        {currentWork || <span className="text-stone-700 italic">No context yet</span>}
      </div>
    </div>
  )
}

function ContextDisplay({ label, content, onEdit }: { label: string; content?: string; onEdit: () => void }) {
  return (
    <div className="mb-4 group">
      <div className="flex items-center gap-2 mb-1">
        <span className="text-[9px] uppercase tracking-wide text-stone-600 font-medium">{label}</span>
        <button onClick={onEdit}
          className="text-stone-700 hover:text-stone-400 opacity-0 group-hover:opacity-100 transition-opacity text-[10px]">
          ✎ edit
        </button>
      </div>
      <div className="text-xs text-stone-400 leading-relaxed">
        {content || <span className="text-stone-700 italic">Not set</span>}
      </div>
    </div>
  )
}

function ContextEditor({ contextType, current, slug, onSaved, onCancel }: {
  contextType: string
  current?: string
  slug: string
  onSaved: () => void
  onCancel: () => void
}) {
  const [value, setValue] = useState(current || '')
  const [saving, setSaving] = useState(false)
  async function save() {
    if (!value.trim()) return
    setSaving(true)
    try {
      await projectsApi.postContext(slug, {
        context_type: contextType,
        content: value.trim(),
        source: 'jonathan',
      })
      onSaved()
    } finally {
      setSaving(false)
    }
  }
  return (
    <div className="mb-4">
      <div className="text-[9px] uppercase tracking-wide text-stone-600 font-medium mb-2">
        {contextType.replace('_', ' ')}
      </div>
      <textarea
        autoFocus
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => { if (e.key === 'Escape') onCancel() }}
        className="w-full bg-stone-950 border border-stone-700 rounded px-3 py-2 text-xs text-stone-200 placeholder:text-stone-600 focus:outline-none focus:border-orange-400/50 resize-none"
        rows={3}
      />
      <div className="flex gap-2 mt-2">
        <button onClick={save} disabled={saving}
          className="text-[11px] px-3 py-1 rounded bg-orange-400/10 border border-orange-400/30 text-orange-400 hover:bg-orange-400/20 disabled:opacity-50 transition-colors">
          {saving ? 'Saving...' : 'Save'}
        </button>
        <button onClick={onCancel}
          className="text-[11px] px-3 py-1 rounded bg-stone-950 border border-stone-700 text-stone-500 hover:text-stone-300 transition-colors">
          Cancel
        </button>
      </div>
    </div>
  )
}

function ExpandedCard({ project, onClose, onContextSaved }: {
  project: Project
  onClose: () => void
  onContextSaved: () => void
}) {
  const [editingType, setEditingType] = useState<string | null>(null)
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
          {project.has_guide && (
            <Link to={`/projects/${project.slug}/guide`}
              className="text-orange-400/70 hover:text-orange-400 transition-colors"
              onClick={(e) => e.stopPropagation()}>
              Docs ↗
            </Link>
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
        {/* Column 1: Context */}
        <div className="p-6">
          <div className="text-[9px] uppercase tracking-wider text-stone-600 font-semibold mb-4">Context</div>
          {editingType === 'current_work' ? (
            <ContextEditor contextType="current_work" current={ctx.current_work?.content} slug={project.slug}
              onSaved={() => { setEditingType(null); onContextSaved() }}
              onCancel={() => setEditingType(null)} />
          ) : (
            <ContextDisplay label="now" content={ctx.current_work?.content}
              onEdit={() => setEditingType('current_work')} />
          )}
          {editingType === 'next_step' ? (
            <ContextEditor contextType="next_step" current={ctx.next_step?.content} slug={project.slug}
              onSaved={() => { setEditingType(null); onContextSaved() }}
              onCancel={() => setEditingType(null)} />
          ) : (
            <ContextDisplay label="next" content={ctx.next_step?.content}
              onEdit={() => setEditingType('next_step')} />
          )}
        </div>

        {/* Column 2: Latest summary */}
        <div className="p-6">
          <div className="text-[9px] uppercase tracking-wider text-stone-600 font-semibold mb-4">Latest summary</div>
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
            <div className="text-xs text-stone-700 italic">No summary yet</div>
          )}
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
  const [refreshKey, setRefreshKey] = useState(0)

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
  }, [refreshKey])

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
                  onContextSaved={() => setRefreshKey((k) => k + 1)}
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
