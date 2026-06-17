import type { JSX, ReactNode } from 'react'
import { cn } from './cn'

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
      <div className="flex flex-1 overflow-hidden">{children}</div>
    </div>
  )
}
