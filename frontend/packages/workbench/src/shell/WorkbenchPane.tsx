import type { JSX, ReactNode } from 'react'
import { cn } from '../lib/cn'

/** Shipped for the deferred ace-web adoption; not yet consumed in canopy. */
/** A generic bordered side panel (e.g. a detail or chat column). */
export function WorkbenchPane({
  width,
  side = 'left',
  children,
  className,
}: {
  width?: string
  side?: 'left' | 'right'
  children: ReactNode
  className?: string
}): JSX.Element {
  return (
    <section
      className={cn(
        'shrink-0 bg-background',
        side === 'right' ? 'border-l border-border' : 'border-r border-border',
        width,
        className,
      )}
    >
      {children}
    </section>
  )
}
