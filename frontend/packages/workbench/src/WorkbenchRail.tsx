import type { JSX, ReactNode } from 'react'
import { cn } from './cn'

/**
 * The bordered left rail chrome. Header slot (identity / title / filters) over a
 * scrollable body that takes arbitrary children (a tree or a flat list).
 */
export function WorkbenchRail({
  width = 'w-64',
  header,
  children,
  className,
}: {
  width?: string
  header?: ReactNode
  children: ReactNode
  className?: string
}): JSX.Element {
  return (
    <aside
      className={cn(
        'flex shrink-0 flex-col border-r border-border bg-background',
        width,
        className,
      )}
    >
      {header && <div className="border-b border-border">{header}</div>}
      <div className="flex-1 overflow-y-auto">{children}</div>
    </aside>
  )
}
