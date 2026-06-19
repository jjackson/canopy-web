import type { JSX, ReactNode } from 'react'

/** The per-section bar inside the main area: title + count + right action. */
export function WorkbenchSubHeader({
  title,
  count,
  action,
}: {
  title: string
  count?: number
  action?: ReactNode
}): JSX.Element {
  return (
    <div className="mb-6 flex items-center justify-between gap-3 border-b border-border pb-4">
      <div className="flex min-w-0 items-baseline gap-2">
        <h1 className="text-base font-semibold text-foreground">{title}</h1>
        {count !== undefined && (
          <span className="text-[12px] text-muted-foreground">{count}</span>
        )}
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </div>
  )
}
