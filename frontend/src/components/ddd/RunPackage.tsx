import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  getRun,
  type DddLink,
  type DddRunNarrative,
  type DddRunPackage,
} from '@/api/ddd'

function fmtDate(iso: string | null): string {
  if (!iso) return ''
  try {
    return new Date(iso).toLocaleString(undefined, {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
    })
  } catch {
    return iso
  }
}

function Section({
  title,
  subtitle,
  children,
}: {
  title: string
  subtitle?: string
  children: React.ReactNode
}) {
  return (
    <section className="mt-6">
      <div className="mb-2 flex items-baseline gap-2">
        <h2 className="text-[10px] font-semibold uppercase tracking-wider text-stone-500">
          {title}
        </h2>
        {subtitle && <span className="text-[11px] text-stone-600">{subtitle}</span>}
        <span className="h-px flex-1 bg-stone-800" />
      </div>
      {children}
    </section>
  )
}

function Empty({ children }: { children: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-dashed border-stone-800 px-4 py-6 text-center text-xs text-stone-600">
      {children}
    </div>
  )
}

function NarrativeBlock({ narrative }: { narrative: DddRunNarrative }) {
  return (
    <div className="rounded-xl border border-stone-800 bg-stone-900 p-5">
      {narrative.story && (
        <p className="mb-4 whitespace-pre-line text-sm leading-relaxed text-stone-200">
          {narrative.story}
        </p>
      )}
      {narrative.narration.length > 0 && (
        <ol className="flex flex-col gap-2">
          {narrative.narration.map((n, i) => {
            const persona = n.persona ? narrative.personas?.[n.persona] : undefined
            return (
              <li
                key={n.id ?? i}
                className="rounded-lg border border-stone-800 bg-stone-950/40 px-3 py-2"
              >
                <div className="mb-0.5 flex items-center gap-2">
                  <span className="text-[10px] font-mono text-stone-600">
                    {n.scene ?? i + 1}
                  </span>
                  {n.title && (
                    <span className="text-xs font-medium text-stone-300">{n.title}</span>
                  )}
                  {persona?.name && (
                    <span
                      className="text-[10px] text-orange-300/80"
                      title={persona.role || ''}
                    >
                      {persona.name}
                    </span>
                  )}
                </div>
                <p className="text-xs leading-relaxed text-stone-400">{n.text}</p>
              </li>
            )
          })}
        </ol>
      )}
    </div>
  )
}

function LinksBlock({ links }: { links: DddLink[] }) {
  const sibling = links.filter((l) => l.kind === 'narrative' || l.kind === 'companion')
  const reference = links.filter((l) => l.kind === 'reference')
  const row = (l: DddLink) => (
    <a
      key={`${l.kind}:${l.url}`}
      href={l.url}
      target="_blank"
      rel="noopener noreferrer"
      className="group flex items-center gap-3 rounded-lg border border-stone-800 bg-stone-950/40 px-3 py-2 transition-colors hover:border-stone-700 hover:bg-stone-950/70"
    >
      {(l.kind === 'narrative' || l.kind === 'companion') && (
        <span aria-hidden className="shrink-0 text-sm">
          {l.kind === 'narrative' ? '📖' : '🎞️'}
        </span>
      )}
      <span className="flex-1 truncate text-xs text-stone-300">{l.label}</span>
      <span
        aria-hidden
        className="shrink-0 text-[11px] text-stone-600 transition-colors group-hover:text-orange-400"
      >
        ↗
      </span>
    </a>
  )
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      {sibling.length > 0 && (
        <div className="flex flex-col gap-2">
          <h3 className="text-[9px] uppercase tracking-wider text-stone-600">
            Narrative &amp; companion
          </h3>
          {sibling.map(row)}
        </div>
      )}
      {reference.length > 0 && (
        <div className="flex flex-col gap-2">
          <h3 className="text-[9px] uppercase tracking-wider text-stone-600">
            Explore in the app
          </h3>
          {reference.map(row)}
        </div>
      )}
    </div>
  )
}

export function RunPackage({ runId }: { runId: string }) {
  const [run, setRun] = useState<DddRunPackage | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setRun(null)
    setError(null)
    getRun(runId)
      .then((d) => !cancelled && setRun(d))
      .catch((e) => !cancelled && setError(String(e.message || e)))
    return () => {
      cancelled = true
    }
  }, [runId])

  if (error)
    return <div className="p-8 text-sm text-red-400/90">Error: {error}</div>
  if (!run) return <div className="p-8 text-sm text-stone-500">Loading run…</div>

  return (
    <div className="mx-auto max-w-4xl px-8 py-6">
      <header className="flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <div className="text-[11px] uppercase tracking-wider text-stone-500">
            {run.narrative_slug}
          </div>
          <h1 className="font-mono text-xl font-semibold text-stone-100">
            {run.run_id}
          </h1>
        </div>
        <div className="flex items-center gap-3 text-xs text-stone-500">
          {run.phase && (
            <span className="rounded border border-stone-700 bg-stone-800/60 px-2 py-0.5 text-stone-300">
              {run.phase}
            </span>
          )}
          <span>{fmtDate(run.latest_at)}</span>
        </div>
      </header>

      <Section title="Video">
        {run.video ? (
          <div className="overflow-hidden rounded-xl border border-stone-800 bg-black">
            <video
              src={run.video.content_url}
              controls
              className="max-h-[70vh] w-full bg-black"
            />
          </div>
        ) : (
          <Empty>No video for this run.</Empty>
        )}
      </Section>

      <Section title="Walkthrough">
        {run.deck ? (
          <div className="overflow-hidden rounded-xl border border-stone-800 bg-white">
            <iframe
              src={run.deck.content_url}
              title={run.deck.title}
              sandbox="allow-scripts allow-same-origin"
              className="h-[70vh] w-full bg-white"
            />
          </div>
        ) : (
          <Empty>No walkthrough deck for this run.</Empty>
        )}
      </Section>

      <Section title="Narrative">
        {run.narrative && (run.narrative.story || run.narrative.narration.length > 0) ? (
          <NarrativeBlock narrative={run.narrative} />
        ) : (
          <Empty>No narrative recorded for this run yet.</Empty>
        )}
      </Section>

      {run.links.length > 0 && (
        <Section title="Links">
          <LinksBlock links={run.links} />
        </Section>
      )}

      <Section title="All artifacts" subtitle={`${run.all_artifacts.length} uploaded`}>
        <div className="flex flex-col gap-1">
          {run.all_artifacts.map((a) => (
            <Link
              key={a.id}
              to={a.viewer_url}
              className="group flex items-center gap-3 rounded-lg border border-stone-800 bg-stone-950/40 px-3 py-1.5 text-xs transition-colors hover:border-stone-700 hover:bg-stone-950/70"
            >
              <span className="w-12 shrink-0 font-mono text-[10px] text-stone-600">
                {a.kind}
              </span>
              {a.role && (
                <span className="shrink-0 rounded bg-stone-800 px-1.5 py-0.5 text-[9px] text-stone-400">
                  {a.role}
                </span>
              )}
              <span className="flex-1 truncate text-stone-300">{a.title}</span>
              <span className="shrink-0 text-stone-600">{fmtDate(a.created_at)}</span>
            </Link>
          ))}
        </div>
      </Section>

      {run.previous_runs.length > 0 && (
        <Section title="Previous runs">
          <div className="flex flex-wrap gap-2">
            {run.previous_runs.map((p) => (
              <Link
                key={p.run_id}
                to={`/ddd/${encodeURIComponent(run.narrative_slug)}/${encodeURIComponent(p.run_id)}`}
                className="rounded-md border border-stone-800 bg-stone-900 px-2.5 py-1 font-mono text-[11px] text-stone-400 transition-colors hover:border-stone-700 hover:text-stone-200"
              >
                {p.run_id}
              </Link>
            ))}
          </div>
        </Section>
      )}
    </div>
  )
}
