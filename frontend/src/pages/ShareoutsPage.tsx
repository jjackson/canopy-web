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
  const opts: Intl.DateTimeFormatOptions = { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' }
  const s = parseLocalDate(start).toLocaleDateString(undefined, opts)
  if (start === end) return s
  const e = parseLocalDate(end).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
  return `${s} – ${e}`
}

function Markdown({ children }: { children: string }) {
  return (
    <div className="prose prose-invert prose-sm max-w-none leading-relaxed prose-headings:text-stone-200 prose-headings:font-semibold prose-headings:text-[13px] prose-headings:uppercase prose-headings:tracking-wide prose-headings:mt-4 prose-headings:mb-1.5 prose-p:text-stone-300 prose-p:my-2 prose-li:text-stone-300 prose-li:my-0.5 prose-ul:my-2 prose-strong:text-stone-100 prose-a:text-orange-400 prose-a:no-underline hover:prose-a:underline prose-code:text-orange-300 prose-code:bg-stone-950 prose-code:px-1 prose-code:py-0.5 prose-code:rounded prose-code:text-[0.85em] prose-code:before:content-none prose-code:after:content-none">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{children}</ReactMarkdown>
    </div>
  )
}

function LinkChips({ links }: { links: Shareout['links'] }) {
  if (!links || links.length === 0) return null
  return (
    <div className="flex flex-wrap gap-1.5 mt-3">
      {links.map((l, i) => (
        <a
          key={i}
          href={l.url}
          target="_blank"
          rel="noreferrer"
          className="inline-flex items-center gap-1 text-[11px] font-medium text-stone-300 hover:text-orange-300 bg-stone-950/80 border border-stone-700/60 hover:border-orange-400/50 px-2 py-1 rounded-md transition-colors"
        >
          <span className="text-orange-400/70">↗</span>
          {l.label}
        </a>
      ))}
    </div>
  )
}

const PR_STATE_STYLE: Record<string, string> = {
  MERGED: 'text-violet-300 bg-violet-400/10 border-violet-400/30',
  OPEN: 'text-green-300 bg-green-400/10 border-green-400/30',
  CLOSED: 'text-stone-400 bg-stone-700/20 border-stone-600/40',
}

function AllPRs({ prs }: { prs: Shareout['all_prs'] }) {
  if (!prs || prs.length === 0) return null
  return (
    <details className="mt-3 group">
      <summary className="cursor-pointer select-none text-[11px] font-medium text-stone-400 hover:text-stone-200 list-none flex items-center gap-1.5">
        <span className="transition-transform group-open:rotate-90 text-stone-600">▶</span>
        All {prs.length} PR{prs.length === 1 ? '' : 's'} this period
      </summary>
      <ul className="mt-2 ml-1 space-y-1 border-l border-stone-800 pl-3">
        {prs.map((pr, i) => (
          <li key={i} className="flex items-start gap-2 text-[12px]">
            <span
              className={`shrink-0 mt-0.5 text-[9px] font-semibold uppercase tracking-wide px-1.5 py-0.5 rounded border ${PR_STATE_STYLE[pr.state ?? ''] ?? 'text-stone-400 bg-stone-800/40 border-stone-700/50'}`}
            >
              {pr.state || '—'}
            </span>
            <a
              href={pr.url}
              target="_blank"
              rel="noreferrer"
              className="text-stone-400 hover:text-orange-300 leading-snug"
            >
              {pr.number != null && <span className="text-stone-600">#{pr.number} </span>}
              {pr.title}
            </a>
          </li>
        ))}
      </ul>
    </details>
  )
}

function RollupCard({ shareout }: { shareout: Shareout }) {
  return (
    <div className="bg-gradient-to-b from-stone-900 to-stone-900/60 border border-orange-400/30 rounded-xl p-5 sm:p-6 shadow-lg shadow-black/20">
      <div className="flex items-center gap-2 mb-3">
        <span className="text-[10px] font-semibold uppercase tracking-wider text-orange-300 bg-orange-400/10 border border-orange-400/20 px-2 py-0.5 rounded">
          Roll-up
        </span>
      </div>
      <h3 className="text-lg font-semibold text-stone-50 mb-2 leading-snug">{shareout.title}</h3>
      {shareout.summary && (
        <p className="text-sm text-stone-400 mb-3 leading-relaxed">{shareout.summary}</p>
      )}
      <Markdown>{shareout.content}</Markdown>
      <LinkChips links={shareout.links} />
    </div>
  )
}

function ProjectCard({ shareout }: { shareout: Shareout }) {
  return (
    <details className="group bg-stone-900/70 border border-stone-800 rounded-xl overflow-hidden open:border-stone-700 open:bg-stone-900 transition-colors">
      <summary className="cursor-pointer select-none list-none p-4 sm:p-5 hover:bg-stone-800/30 transition-colors">
        <div className="flex items-start gap-3">
          <span className="mt-1 shrink-0 text-stone-600 text-xs transition-transform group-open:rotate-90">▶</span>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2 flex-wrap">
              {shareout.project_slug && (
                <span className="text-[10px] font-semibold uppercase tracking-wide text-stone-400 bg-stone-800 px-1.5 py-0.5 rounded">
                  {shareout.project_name ?? shareout.project_slug}
                </span>
              )}
              {shareout.all_prs && shareout.all_prs.length > 0 && (
                <span className="text-[10px] text-stone-600">
                  {shareout.all_prs.length} PR{shareout.all_prs.length === 1 ? '' : 's'}
                </span>
              )}
            </div>
            <h3 className="text-[15px] font-semibold text-stone-100 mt-1.5 leading-snug">{shareout.title}</h3>
            {shareout.summary && (
              <p className="text-[13px] text-stone-400 mt-1 leading-relaxed">{shareout.summary}</p>
            )}
          </div>
        </div>
      </summary>
      <div className="px-4 sm:px-5 pb-5 pl-10 sm:pl-11">
        <Markdown>{shareout.content}</Markdown>
        <LinkChips links={shareout.links} />
        <AllPRs prs={shareout.all_prs} />
        {shareout.project_slug && (
          <Link
            to={`/?expand=${encodeURIComponent(shareout.project_slug)}`}
            className="inline-block mt-3 text-[11px] text-stone-500 hover:text-orange-400 transition-colors"
          >
            Open {shareout.project_name ?? shareout.project_slug} on the dashboard →
          </Link>
        )}
      </div>
    </details>
  )
}

function PeriodBlock({ period }: { period: ShareoutPeriod }) {
  const prTotal = period.projects.reduce((n, p) => n + (p.all_prs?.length ?? 0), 0)
  return (
    <section className="mb-12">
      <div className="flex items-baseline gap-3 mb-4">
        <h2 className="text-base font-semibold text-stone-200">
          {formatPeriod(period.periodStart, period.periodEnd)}
        </h2>
        <span className="text-[11px] text-stone-600">
          {period.projects.length} project{period.projects.length === 1 ? '' : 's'}
          {prTotal > 0 && ` · ${prTotal} PRs`}
        </span>
        <div className="flex-1 h-px bg-gradient-to-r from-stone-800 to-transparent" />
      </div>
      <div className="space-y-3">
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
    <div className="max-w-3xl mx-auto px-1">
      <div className="mb-8">
        <h1 className="text-xl font-semibold text-stone-100">Shareouts</h1>
        <p className="text-[13px] text-stone-500 mt-1">
          What shipped, why it matters, and how to leverage it — by date. Tap a project to read the briefing.
        </p>
      </div>

      {error && (
        <div className="flex items-center justify-center h-48 text-red-400 text-sm">{error}</div>
      )}

      {loading && (
        <div className="space-y-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <div
              key={i}
              className="bg-stone-900 border border-stone-800 rounded-xl p-5 animate-pulse"
              style={{ animationDelay: `${i * 80}ms` }}
            >
              <div className="h-3 bg-stone-800 rounded w-24 mb-3" />
              <div className="h-4 bg-stone-800 rounded w-2/3 mb-2" />
              <div className="h-3 bg-stone-800/70 rounded w-full" />
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
