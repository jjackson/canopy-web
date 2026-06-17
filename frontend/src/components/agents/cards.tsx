// Shared presentational pieces for the Agent Workspace sections. Extracted
// verbatim from the old single-column AgentWorkspacePage so the lazy-loaded
// section routes (overview / syncs / work-products / skills) can share them.
// Styling is preserved exactly as it was inline on the page.

import type {
  AgentSkillOut,
  AgentSyncOut,
  AgentWorkProductOut,
} from '@/api/agents'

export function formatDate(s: string): string {
  return new Date(s).toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  })
}

export function formatPeriod(start: string, end: string): string {
  const s = formatDate(start)
  const e = formatDate(end)
  return s === e ? s : `${s} – ${e}`
}

export function CountStat({ value, label }: { value: number; label: string }) {
  return (
    <div className="flex flex-col">
      <span className="text-lg font-semibold text-stone-100 leading-none">{value}</span>
      <span className="text-[10px] uppercase tracking-wide text-stone-600 mt-1">{label}</span>
    </div>
  )
}

export function SectionHeading({ label, count }: { label: string; count?: number }) {
  return (
    <div className="flex items-baseline gap-2 mb-3 mt-8 first:mt-0">
      <h2 className="text-[11px] font-bold uppercase tracking-[0.08em] text-orange-300">{label}</h2>
      {count !== undefined && <span className="text-[11px] text-stone-600">{count}</span>}
    </div>
  )
}

// "work: C+" → an outlined badge. Generic so any grade dimension renders.
function GradeBadge({ dimension, grade }: { dimension: string; grade: string }) {
  return (
    <span className="inline-flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wide text-stone-300 bg-stone-950/80 border border-stone-700/60 px-2 py-0.5 rounded">
      <span className="text-stone-500">{dimension}:</span>
      <span className="text-orange-300">{grade}</span>
    </span>
  )
}

function OpenDocChip({ url, label }: { url: string; label: string }) {
  if (!url) return null
  return (
    <a
      href={url}
      target="_blank"
      rel="noreferrer"
      className="inline-flex items-center gap-1 text-[11px] font-medium text-stone-300 hover:text-orange-300 bg-stone-950/80 border border-stone-700/60 hover:border-orange-400/50 px-2.5 py-1 rounded-md transition-colors"
    >
      <span className="text-orange-400/70">↗</span>
      {label}
    </a>
  )
}

export function SyncCard({ sync }: { sync: AgentSyncOut }) {
  const grades = Object.entries(sync.self_grades ?? {})
  return (
    <div className="bg-stone-900/70 border border-stone-800 rounded-xl p-5">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[11px] text-stone-500">{formatPeriod(sync.period_start, sync.period_end)}</p>
          <h3 className="text-[15px] font-semibold text-stone-100 mt-0.5 leading-snug">{sync.title}</h3>
        </div>
        <OpenDocChip url={sync.doc_url} label="Open in Google Docs" />
      </div>
      {sync.summary && (
        <p className="text-[13px] text-stone-400 leading-relaxed mt-2">{sync.summary}</p>
      )}
      {grades.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mt-3">
          {grades.map(([dimension, grade]) => (
            <GradeBadge key={dimension} dimension={dimension} grade={grade} />
          ))}
        </div>
      )}
    </div>
  )
}

export function WorkProductCard({ wp }: { wp: AgentWorkProductOut }) {
  return (
    <a
      href={wp.url}
      target="_blank"
      rel="noreferrer"
      className="group block bg-stone-900/70 border border-stone-800 rounded-xl p-4 hover:border-orange-400/40 hover:bg-stone-900 transition-colors"
    >
      <div className="flex items-start gap-2">
        <h3 className="text-[14px] font-semibold text-stone-100 leading-snug group-hover:text-orange-300 transition-colors min-w-0 flex-1">
          {wp.title}
        </h3>
        <span className="text-orange-400/70 text-xs shrink-0">↗</span>
      </div>
      {wp.kind && (
        <span className="inline-block mt-2 text-[10px] font-semibold uppercase tracking-wide text-stone-400 bg-stone-800 px-1.5 py-0.5 rounded">
          {wp.kind}
        </span>
      )}
      {wp.description && (
        <p className="text-[12px] text-stone-400 leading-relaxed mt-2 line-clamp-3">{wp.description}</p>
      )}
      {wp.tags && wp.tags.length > 0 && (
        <div className="flex flex-wrap gap-1 mt-2">
          {wp.tags.map((t) => (
            <span key={t} className="text-[10px] text-stone-500 bg-stone-950/60 border border-stone-800 px-1.5 py-0.5 rounded">
              {t}
            </span>
          ))}
        </div>
      )}
    </a>
  )
}

export function SkillCard({ skill }: { skill: AgentSkillOut }) {
  return (
    <div className="bg-stone-900/70 border border-stone-800 rounded-xl p-4">
      <div className="flex items-start justify-between gap-2">
        <h3 className="text-[14px] font-semibold text-stone-100 leading-snug min-w-0">{skill.name}</h3>
        <OpenDocChip url={skill.url} label="SKILL.md" />
      </div>
      {skill.description && (
        <p className="text-[12px] text-stone-400 leading-relaxed mt-2">{skill.description}</p>
      )}
      {skill.improvement_note && (
        <p className="text-[12px] text-stone-300 leading-relaxed mt-2 pl-3 border-l-2 border-orange-400/40">
          <span className="text-[10px] font-semibold uppercase tracking-wide text-orange-300/80 mr-1">
            Improvement
          </span>
          {skill.improvement_note}
        </p>
      )}
    </div>
  )
}
