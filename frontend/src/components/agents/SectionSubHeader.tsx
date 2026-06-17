import type { ReactNode } from 'react'

/**
 * The consistent bar at the top of every Agent Workspace section: a title, an
 * optional count, and an optional contextual action on the right. Sits inside
 * the scrolling main area above each section's content.
 */
export function SectionSubHeader({
  title,
  count,
  action,
}: {
  title: string
  count?: number
  action?: ReactNode
}) {
  return (
    <div className="flex items-center justify-between gap-3 pb-4 mb-6 border-b border-stone-800">
      <div className="flex items-baseline gap-2 min-w-0">
        <h1 className="text-base font-semibold text-stone-100">{title}</h1>
        {count !== undefined && (
          <span className="text-[12px] text-stone-600">{count}</span>
        )}
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </div>
  )
}

/** A pulsing card placeholder used while a section lazy-loads its own data. */
export function SectionSkeleton({ rows = 3 }: { rows?: number }) {
  return (
    <div className="animate-pulse space-y-3">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="bg-stone-900 border border-stone-800 rounded-xl p-5">
          <div className="h-4 bg-stone-800 rounded w-2/3 mb-2" />
          <div className="h-3 bg-stone-800/70 rounded w-full" />
        </div>
      ))}
    </div>
  )
}
