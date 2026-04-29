import { useEffect, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { AnimatePresence, LayoutGroup, motion } from 'framer-motion'
import { type Project, projectsApi } from '@/api/projects'
import {
  type Insight,
  insightsApi,
  parseInsightBody,
  parseInsightCategory,
} from '@/api/insights'
import { CategoryBadge } from '@/components/InsightChip'

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

// A project is considered stale (and dropped behind the "Show stale" toggle)
// if its DB status is `stale` or `archived`, OR if its most recent summary is
// older than 7 days. We mirror the per-tile staleness threshold used on the
// collapsed tile's left-border so the visual hint and the page-level grouping
// stay in sync.
const STALE_DAYS = 7
function isProjectStale(p: Project): boolean {
  if (p.status === 'stale' || p.status === 'archived') return true
  const summaryDate = p.latest_context?.summary?.created_at
  if (!summaryDate) return false
  const ageDays = (Date.now() - new Date(summaryDate).getTime()) / (1000 * 60 * 60 * 24)
  return ageDays > STALE_DAYS
}

function InsightBadge({ slug, count, compact }: { slug: string; count: number; compact?: boolean }) {
  if (!count) return null
  return (
    <Link
      to={`/insights?project=${encodeURIComponent(slug)}`}
      onClick={(e) => e.stopPropagation()}
      title={`${count} insight${count === 1 ? '' : 's'} for this project — click to filter the feed`}
      className={`font-semibold text-orange-400/90 hover:text-orange-300 bg-orange-400/10 border border-orange-400/25 rounded transition-colors shrink-0 ${
        compact ? 'text-[9px] px-1.5 py-0.5' : 'text-[10px] px-2 py-0.5'
      }`}
    >
      {count}{compact ? '' : ` insight${count === 1 ? '' : 's'}`}
    </Link>
  )
}

// Inline insight row rendered atop the expanded project card. Each row mirrors
// the standalone /insights feed's card semantics (category badge + body + ✕),
// but compacted into the card so triage can happen without leaving the
// dashboard. Dismiss calls back through to the parent so the project's
// `insight_count` badge can decrement live without a refetch.
function InlineInsightStrip({
  insights,
  onDismiss,
}: {
  insights: Insight[]
  onDismiss: (id: number) => void
}) {
  if (!insights.length) return null
  return (
    <div className="px-6 py-4 bg-stone-950/40 border-b border-stone-800">
      <div className="text-[9px] uppercase tracking-wider text-stone-600 font-semibold mb-3">
        Insights ({insights.length})
      </div>
      <div className="space-y-2">
        <AnimatePresence initial={false}>
          {insights.map((insight) => {
            const category = parseInsightCategory(insight.content)
            const body = parseInsightBody(insight.content)
            return (
              <motion.div
                key={insight.id}
                layout
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, x: -32, transition: { duration: 0.18 } }}
                transition={{ type: 'spring', stiffness: 400, damping: 35 }}
                className="flex items-start gap-3 text-xs text-stone-300"
              >
                <div className="pt-0.5 shrink-0">
                  <CategoryBadge category={category} />
                </div>
                <p className="flex-1 leading-relaxed">{body}</p>
                <button
                  onClick={(e) => { e.stopPropagation(); onDismiss(insight.id) }}
                  className="text-stone-700 hover:text-stone-400 text-sm shrink-0 leading-none mt-0.5"
                  aria-label="Dismiss insight"
                  title="Dismiss"
                >
                  ✕
                </button>
              </motion.div>
            )
          })}
        </AnimatePresence>
      </div>
    </div>
  )
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
          <InsightBadge slug={project.slug} count={project.insight_count || 0} compact />
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

function ExpandedCard({ project, onClose, scrollIntoViewOnMount, insights, onDismissInsight }: {
  project: Project
  onClose: () => void
  scrollIntoViewOnMount?: boolean
  insights: Insight[]
  onDismissInsight: (id: number) => void
}) {
  const [skillsExpanded, setSkillsExpanded] = useState(false)
  const cardRef = useRef<HTMLDivElement | null>(null)
  const ctx = project.latest_context || {}
  const skills = project.skills || []

  useEffect(() => {
    if (scrollIntoViewOnMount && cardRef.current) {
      cardRef.current.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }
    // Only run on mount; the parent flips this flag exactly once per deep link.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <div
      ref={cardRef}
      className="bg-stone-900 border border-stone-700 rounded-xl overflow-hidden"
      onClick={(e) => e.stopPropagation()}
    >
      {/* Header */}
      <div className="flex items-center gap-3 px-6 py-4 border-b border-stone-800">
        <StatusDot status={project.status} />
        <span className="text-base font-bold text-stone-100">{project.name}</span>
        <InsightBadge slug={project.slug} count={project.insight_count || 0} />
        {project.visibility === 'private' && <PrivateBadge />}
        {project.deploy_url && <DeployBadge url={project.deploy_url} />}
        <div className="ml-auto flex items-center gap-4 text-[11px]">
          <Link
            to={`/insights?project=${encodeURIComponent(project.slug)}`}
            className="text-orange-400/70 hover:text-orange-400 transition-colors"
            onClick={(e) => e.stopPropagation()}
            title={`See insights for ${project.name}`}
          >
            View insights →
          </Link>
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

      {/* Inline insights — triaged in place, decrements the badge above on dismiss */}
      <InlineInsightStrip insights={insights} onDismiss={onDismissInsight} />

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
  const [searchParams, setSearchParams] = useSearchParams()
  // The slug that the URL asked us to expand; we strip it from the URL once
  // applied so refreshing the page doesn't keep re-scrolling.
  const [pendingScrollSlug, setPendingScrollSlug] = useState<string | null>(null)
  // Stale projects (status=stale|archived OR summary >7d old) are tucked behind
  // this toggle so the daily-check-in surface leads with what's actually hot.
  const [showStale, setShowStale] = useState(false)
  // All open insights, grouped by project_slug. Bulk-fetched alongside the
  // projects list so an expanded card can render its insights without a
  // per-card request. Dismiss removes from this map AND decrements the
  // matching project's `insight_count`, so the orange "N insights" pill on
  // the tile updates live in lockstep with the inline strip.
  const [insightsByProject, setInsightsByProject] = useState<Record<string, Insight[]>>({})

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    void (async () => {
      try {
        const [projectsData, insightsData] = await Promise.all([
          projectsApi.list(),
          insightsApi.list({ limit: 200 }).catch(() => [] as Insight[]),
        ])
        if (cancelled) return
        setProjects(projectsData)
        const grouped: Record<string, Insight[]> = {}
        for (const insight of insightsData) {
          if (!grouped[insight.project_slug]) grouped[insight.project_slug] = []
          grouped[insight.project_slug].push(insight)
        }
        setInsightsByProject(grouped)
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Failed to load projects')
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => { cancelled = true }
  }, [])

  async function handleDismissInsight(slug: string, id: number) {
    // Optimistic local update — the card animates the row out immediately and
    // the badge count decrements in the same frame. If the network call
    // fails, we restore by refetching the full insights list (rare).
    setInsightsByProject((prev) => {
      const list = prev[slug] || []
      return { ...prev, [slug]: list.filter((i) => i.id !== id) }
    })
    setProjects((prev) =>
      prev.map((p) =>
        p.slug === slug
          ? { ...p, insight_count: Math.max(0, (p.insight_count || 0) - 1) }
          : p,
      ),
    )
    try {
      await insightsApi.dismiss(id)
    } catch {
      // Best-effort recovery: refetch insights so the UI matches server truth.
      try {
        const fresh = await insightsApi.list({ limit: 200 })
        const grouped: Record<string, Insight[]> = {}
        for (const insight of fresh) {
          if (!grouped[insight.project_slug]) grouped[insight.project_slug] = []
          grouped[insight.project_slug].push(insight)
        }
        setInsightsByProject(grouped)
        setProjects((prev) =>
          prev.map((p) => ({
            ...p,
            insight_count: (grouped[p.slug] || []).length,
          })),
        )
      } catch {
        // Give up silently; user can refresh the page.
      }
    }
  }

  // Handle ?expand=<slug> deep links from the insights feed (and bookmarks).
  // Wait until projects load so we only expand a slug that actually exists.
  useEffect(() => {
    if (loading) return
    const target = searchParams.get('expand')
    if (!target) return
    if (!projects.some((p) => p.slug === target)) {
      // Unknown slug — drop the param silently rather than leaving a stale URL.
      const next = new URLSearchParams(searchParams)
      next.delete('expand')
      setSearchParams(next, { replace: true })
      return
    }
    setExpandedOrder((order) => (order.includes(target) ? order : [target, ...order]))
    setPendingScrollSlug(target)
    const next = new URLSearchParams(searchParams)
    next.delete('expand')
    setSearchParams(next, { replace: true })
    // Clear the scroll flag after the ExpandedCard has had a chance to mount
    // and run its scrollIntoView, so a later collapse+re-expand of the same
    // card doesn't keep auto-scrolling.
    const t = window.setTimeout(() => setPendingScrollSlug(null), 600)
    return () => window.clearTimeout(t)
  }, [loading, projects, searchParams, setSearchParams])

  function expand(slug: string) {
    setExpandedOrder((order) => (order.includes(slug) ? order : [slug, ...order]))
  }

  function collapse(slug: string) {
    setExpandedOrder((order) => order.filter((s) => s !== slug))
    if (pendingScrollSlug === slug) setPendingScrollSlug(null)
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
  const collapsedAll = projects.filter((p) => !expandedSet.has(p.slug))
  // Hot grid leads; stale grid is hidden behind the toggle. Expanded cards
  // are NOT filtered — if the user expanded a stale card, it stays open.
  const collapsedHot = collapsedAll.filter((p) => !isProjectStale(p))
  const collapsedStale = collapsedAll.filter((p) => isProjectStale(p))

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
                  scrollIntoViewOnMount={pendingScrollSlug === project.slug}
                  insights={insightsByProject[project.slug] || []}
                  onDismissInsight={(id) => handleDismissInsight(project.slug, id)}
                />
              </motion.div>
            ))}
          </AnimatePresence>
        </div>

        {/* Collapsed tile grid — active projects */}
        <motion.div
          layout
          className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-2"
          transition={SPRING}
        >
          <AnimatePresence initial={false}>
            {collapsedHot.map((project, i) => (
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

        {/* Stale toggle + (optional) stale grid */}
        {collapsedStale.length > 0 && (
          <div className="mt-6">
            <button
              onClick={() => setShowStale((v) => !v)}
              className="text-[11px] text-stone-500 hover:text-stone-300 transition-colors flex items-center gap-2"
              aria-expanded={showStale}
            >
              <span>{showStale ? '▾' : '▸'}</span>
              <span>{showStale ? 'Hide' : 'Show'} stale ({collapsedStale.length})</span>
            </button>
            {showStale && (
              <motion.div
                layout
                className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-2 mt-3 opacity-70"
                transition={SPRING}
              >
                <AnimatePresence initial={false}>
                  {collapsedStale.map((project, i) => (
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
            )}
          </div>
        )}
      </LayoutGroup>
    </div>
  )
}
