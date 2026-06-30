import type { JSX, ReactNode } from 'react'
import { cn } from '../lib/cn'

/**
 * The bordered left rail chrome. Header slot (identity / title / filters) over a
 * scrollable body that takes arbitrary children (a tree or a flat list).
 */
export function WorkbenchRail({
  // `width` must be a md-prefixed Tailwind width (e.g. `md:w-64`): on phones the
  // rail spans full width and stacks above the main column, so the width only
  // applies once the layout goes side-by-side at md+.
  width = 'md:w-64',
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
        'flex shrink-0 flex-col bg-background',
        // Phone: full-width strip with a capped height so the main column below
        // stays reachable. Desktop: fixed-width left rail with a right border.
        'w-full max-h-[42vh] border-b border-border md:max-h-none md:border-b-0 md:border-r',
        width,
        className,
      )}
    >
      {header && <div className="border-b border-border">{header}</div>}
      <div className="flex-1 overflow-y-auto">{children}</div>
    </aside>
  )
}
