import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { AnimatePresence, motion } from 'framer-motion'
import {
  type Insight,
  type InsightCategory,
  insightsApi,
  parseInsightBody,
  parseInsightCategory,
} from '@/api/insights'

const CATEGORIES = [
  { key: 'all', label: 'All' },
  { key: 'ship_gap', label: 'Ship Gaps' },
  { key: 'hygiene', label: 'Hygiene' },
  { key: 'pattern', label: 'Patterns' },
  { key: 'stale', label: 'Stale' },
  { key: 'opportunity', label: 'Opportunities' },
]

const CATEGORY_STYLES: Record<string, { bg: string; border: string; text: string; label: string }> = {
  ship_gap: { bg: 'bg-amber-400/5', border: 'border-amber-400/20', text: 'text-amber-400', label: 'Ship Gap' },
  hygiene: { bg: 'bg-orange-400/5', border: 'border-orange-400/20', text: 'text-orange-400', label: 'Hygiene' },
  pattern: { bg: 'bg-violet-400/5', border: 'border-violet-400/20', text: 'text-violet-400', label: 'Pattern' },
  stale: { bg: 'bg-stone-400/5', border: 'border-stone-400/20', text: 'text-stone-500', label: 'Stale' },
  opportunity: { bg: 'bg-emerald-400/5', border: 'border-emerald-400/20', text: 'text-emerald-400', label: 'Opportunity' },
}

function CategoryBadge({ category }: { category: InsightCategory | null }) {
  if (!category) return null
  const style = CATEGORY_STYLES[category]
  if (!style) return null
  return (
    <span className={`text-[10px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded border ${style.bg} ${style.border} ${style.text}`}>
      {style.label}
    </span>
  )
}

function InsightCard({ insight, onDismiss }: { insight: Insight; onDismiss: (id: number) => void }) {
  const category = parseInsightCategory(insight.content)
  const body = parseInsightBody(insight.content)
  const style = category ? CATEGORY_STYLES[category] : null

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, x: -40, transition: { duration: 0.2 } }}
      transition={{ type: 'spring', stiffness: 400, damping: 35 }}
      className={`bg-stone-900 border rounded-lg p-4 ${style ? style.border : 'border-stone-800'}`}
    >
      <div className="flex items-start justify-between gap-3 mb-2">
        <div className="flex items-center gap-2 min-w-0">
          <Link
            to="/"
            className="text-xs font-medium text-stone-400 hover:text-orange-400 transition-colors shrink-0"
          >
            {insight.project_name}
          </Link>
          <CategoryBadge category={category} />
        </div>
        <button
          onClick={() => onDismiss(insight.id)}
          className="text-stone-700 hover:text-stone-400 text-sm shrink-0 leading-none"
          aria-label="Dismiss"
        >
          ✕
        </button>
      </div>
      <p className="text-sm text-stone-300 leading-relaxed mb-2">{body}</p>
      <div className="flex items-center gap-2 text-[10px] text-stone-600">
        <span>{insight.source}</span>
        <span>·</span>
        <span>{new Date(insight.created_at).toLocaleDateString()}</span>
      </div>
    </motion.div>
  )
}

function SkeletonCard({ delay }: { delay: number }) {
  return (
    <div
      className="bg-stone-900 border border-stone-800 rounded-lg p-4 animate-pulse"
      style={{ animationDelay: `${delay}ms` }}
    >
      <div className="flex items-center gap-3 mb-3">
        <div className="h-3 bg-stone-800 rounded w-20" />
        <div className="h-4 bg-stone-800 rounded w-16" />
      </div>
      <div className="space-y-2">
        <div className="h-3 bg-stone-800/70 rounded w-full" />
        <div className="h-3 bg-stone-800/70 rounded w-4/5" />
      </div>
      <div className="flex items-center gap-2 mt-3">
        <div className="h-2 bg-stone-800/50 rounded w-24" />
        <div className="h-2 bg-stone-800/50 rounded w-16" />
      </div>
    </div>
  )
}

export function InsightsPage() {
  const [insights, setInsights] = useState<Insight[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [activeFilter, setActiveFilter] = useState('all')

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    void (async () => {
      try {
        const category = activeFilter === 'all' ? undefined : activeFilter
        const data = await insightsApi.list(category)
        if (!cancelled) setInsights(data)
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Failed to load insights')
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => { cancelled = true }
  }, [activeFilter])

  async function handleDismiss(id: number) {
    try {
      await insightsApi.dismiss(id)
      setInsights((prev) => prev.filter((i) => i.id !== id))
    } catch {
      // silent
    }
  }

  return (
    <div className="max-w-3xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-lg font-semibold text-stone-100">Insights</h1>
        <span className="text-xs text-stone-600 bg-stone-900 px-2.5 py-1 rounded">
          {loading ? 'loading...' : `${insights.length} insights`}
        </span>
      </div>

      {/* Category filter tabs */}
      <div className="flex gap-1 mb-6 bg-stone-900 rounded-lg p-1 overflow-x-auto">
        {CATEGORIES.map((cat) => (
          <button
            key={cat.key}
            onClick={() => setActiveFilter(cat.key)}
            className={`text-xs font-medium px-3 py-1.5 rounded transition-colors whitespace-nowrap ${
              activeFilter === cat.key
                ? 'text-stone-100 bg-stone-800'
                : 'text-stone-500 hover:text-stone-300 hover:bg-stone-800/50'
            }`}
          >
            {cat.label}
          </button>
        ))}
      </div>

      {/* Error state */}
      {error && (
        <div className="flex items-center justify-center h-48 text-red-400 text-sm">{error}</div>
      )}

      {/* Loading skeleton */}
      {loading && (
        <div className="space-y-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <SkeletonCard key={i} delay={i * 80} />
          ))}
        </div>
      )}

      {/* Insight feed */}
      {!loading && !error && (
        <div className="space-y-3">
          <AnimatePresence initial={false}>
            {insights.map((insight) => (
              <InsightCard key={insight.id} insight={insight} onDismiss={handleDismiss} />
            ))}
          </AnimatePresence>

          {/* Empty state */}
          {insights.length === 0 && (
            <div className="flex flex-col items-center justify-center h-48 text-center">
              <p className="text-sm text-stone-500 mb-1">No insights yet.</p>
              <p className="text-xs text-stone-700">
                Run <code className="text-orange-400/70 bg-stone-900 px-1.5 py-0.5 rounded">canopy:portfolio-review</code> to generate insights.
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
