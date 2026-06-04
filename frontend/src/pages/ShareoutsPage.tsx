import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import {
  type Shareout,
  type ShareoutPeriod,
  groupByPeriod,
  shareoutsApi,
} from '@/api/shareouts'

// Parse a YYYY-MM-DD date as *local* time (not UTC) so a single-day briefing
// doesn't render as the previous day in negative-offset timezones.
function parseLocalDate(iso: string): Date {
  const [y, m, d] = iso.split('-').map(Number)
  return new Date(y, m - 1, d)
}

function formatPeriod(start: string, end: string): string {
  const opts: Intl.DateTimeFormatOptions = { month: 'short', day: 'numeric', year: 'numeric' }
  const s = parseLocalDate(start).toLocaleDateString(undefined, opts)
  if (start === end) return s
  const e = parseLocalDate(end).toLocaleDateString(undefined, opts)
  return `${s} – ${e}`
}

function Markdown({ children }: { children: string }) {
  return (
    <div className="prose prose-invert prose-sm max-w-none prose-headings:text-stone-100 prose-headings:font-semibold prose-p:text-stone-300 prose-li:text-stone-300 prose-strong:text-stone-100 prose-a:text-orange-400 prose-code:text-orange-300 prose-code:bg-stone-950 prose-code:px-1 prose-code:rounded">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{children}</ReactMarkdown>
    </div>
  )
}

function LinkChips({ links }: { links: Shareout['links'] }) {
  if (!links || links.length === 0) return null
  return (
    <div className="flex flex-wrap gap-2 mt-3">
      {links.map((l, i) => (
        <a
          key={i}
          href={l.url}
          target="_blank"
          rel="noreferrer"
          className="text-[11px] font-medium text-stone-300 hover:text-orange-400 bg-stone-950 border border-stone-800 hover:border-orange-400/40 px-2 py-0.5 rounded transition-colors"
        >
          {l.label}
        </a>
      ))}
    </div>
  )
}

function RollupCard({ shareout }: { shareout: Shareout }) {
  return (
    <div className="bg-stone-900 border border-orange-400/30 rounded-lg p-5">
      <div className="flex items-center gap-2 mb-2">
        <span className="text-[10px] font-semibold uppercase tracking-wide text-orange-400/80 bg-orange-400/10 px-2 py-0.5 rounded">
          Roll-up
        </span>
        <h3 className="text-base font-semibold text-stone-100">{shareout.title}</h3>
      </div>
      {shareout.summary && (
        <p className="text-sm text-stone-400 mb-3">{shareout.summary}</p>
      )}
      <Markdown>{shareout.content}</Markdown>
      <LinkChips links={shareout.links} />
    </div>
  )
}

function ProjectCard({ shareout }: { shareout: Shareout }) {
  return (
    <div className="bg-stone-900 border border-stone-800 rounded-lg p-5">
      <div className="flex items-center justify-between gap-3 mb-2">
        <h3 className="text-base font-semibold text-stone-100">{shareout.title}</h3>
        {shareout.project_slug && (
          <Link
            to={`/?expand=${encodeURIComponent(shareout.project_slug)}`}
            className="text-xs font-medium text-stone-400 hover:text-orange-400 transition-colors shrink-0"
            title={`Open ${shareout.project_name ?? shareout.project_slug} on the dashboard`}
          >
            {shareout.project_name ?? shareout.project_slug}
          </Link>
        )}
      </div>
      {shareout.summary && (
        <p className="text-sm text-stone-400 mb-3">{shareout.summary}</p>
      )}
      <Markdown>{shareout.content}</Markdown>
      <LinkChips links={shareout.links} />
    </div>
  )
}

function PeriodBlock({ period }: { period: ShareoutPeriod }) {
  return (
    <section className="mb-10">
      <div className="flex items-center gap-3 mb-4">
        <h2 className="text-sm font-semibold text-stone-300">
          {formatPeriod(period.periodStart, period.periodEnd)}
        </h2>
        <div className="flex-1 h-px bg-stone-800" />
        <span className="text-[11px] text-stone-600">
          {period.projects.length} project{period.projects.length === 1 ? '' : 's'}
        </span>
      </div>
      <div className="space-y-4">
        {period.rollup && <RollupCard shareout={period.rollup} />}
        {period.projects.map((s) => (
          <ProjectCard key={s.id} shareout={s} />
        ))}
      </div>
    </section>
  )
}

export function ShareoutsPage() {
  const [periods, setPeriods] = useState<ShareoutPeriod[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    void (async () => {
      try {
        const data = await shareoutsApi.list({ limit: 200 })
        if (!cancelled) setPeriods(groupByPeriod(data))
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Failed to load shareouts')
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <div className="max-w-3xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-lg font-semibold text-stone-100">Shareouts</h1>
          <p className="text-xs text-stone-500 mt-0.5">
            What shipped, why it matters, and how to leverage it — by date.
          </p>
        </div>
      </div>

      {error && (
        <div className="flex items-center justify-center h-48 text-red-400 text-sm">{error}</div>
      )}

      {loading && (
        <div className="space-y-4">
          {Array.from({ length: 3 }).map((_, i) => (
            <div
              key={i}
              className="bg-stone-900 border border-stone-800 rounded-lg p-5 animate-pulse"
              style={{ animationDelay: `${i * 80}ms` }}
            >
              <div className="h-4 bg-stone-800 rounded w-48 mb-3" />
              <div className="space-y-2">
                <div className="h-3 bg-stone-800/70 rounded w-full" />
                <div className="h-3 bg-stone-800/70 rounded w-4/5" />
              </div>
            </div>
          ))}
        </div>
      )}

      {!loading && !error && (
        <>
          {periods.map((period) => (
            <PeriodBlock key={period.key} period={period} />
          ))}
          {periods.length === 0 && (
            <div className="flex flex-col items-center justify-center h-48 text-center">
              <p className="text-sm text-stone-500 mb-1">No shareouts yet.</p>
              <p className="text-xs text-stone-700">
                Run{' '}
                <code className="text-orange-400/70 bg-stone-900 px-1.5 py-0.5 rounded">
                  canopy:shareout
                </code>{' '}
                to publish a briefing.
              </p>
            </div>
          )}
        </>
      )}
    </div>
  )
}
