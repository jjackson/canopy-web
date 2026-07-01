import { forwardRef, type ComponentPropsWithoutRef, type ReactNode } from 'react'
import { cn } from '../lib/cn'

/**
 * The scrolling main column. Forwards a ref and arbitrary <main> props so a
 * surface can mark it as a scroll-spy root (e.g. data-ddd-scroll).
 */
export const WorkbenchMain = forwardRef<
  HTMLElement,
  ComponentPropsWithoutRef<'main'> & { children: ReactNode }
>(function WorkbenchMain({ children, className, ...rest }, ref) {
  return (
    <main ref={ref} className={cn('min-h-0 min-w-0 flex-1 overflow-y-auto', className)} {...rest}>
      {children}
    </main>
  )
})
