import type { JSX, ReactNode } from 'react'
import { cn } from '../lib/cn'

/**
 * Full-bleed outer scaffold: optional top header over a body row. The caller
 * composes the body (rail + main + optional side panes) as children, and may
 * wrap <WorkbenchShell> in its own provider (e.g. for scroll-spy).
 */
export function WorkbenchShell({
  header,
  children,
  className,
}: {
  header?: ReactNode
  children: ReactNode
  className?: string
}): JSX.Element {
  return (
    <div className={cn('flex h-full flex-col bg-background text-foreground', className)}>
      {header}
      {/* Rail + main sit side-by-side on desktop; on phones they stack so the
          main column gets full width instead of being crushed by the rail. */}
      <div className="flex flex-1 flex-col overflow-hidden md:flex-row">{children}</div>
    </div>
  )
}
