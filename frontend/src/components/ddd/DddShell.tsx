import type { ReactNode } from 'react'
import { WorkbenchShell, WorkbenchMain } from 'canopy-ui'
import { DddLeftNav } from './DddLeftNav'
import { RunSectionNavProvider } from './runSectionNav'

/**
 * DDD section chrome: the narratives→versions→runs rail + a wide scrolling main.
 * Wrapped in RunSectionNavProvider; the main carries data-ddd-scroll so the run
 * package observes its sections against the right scroll container.
 */
export function DddShell({
  activeSlug,
  activeRunId,
  children,
}: {
  activeSlug?: string
  activeRunId?: string
  children: ReactNode
}) {
  return (
    <RunSectionNavProvider>
      <WorkbenchShell>
        <DddLeftNav activeSlug={activeSlug} activeRunId={activeRunId} />
        <WorkbenchMain data-ddd-scroll>{children}</WorkbenchMain>
      </WorkbenchShell>
    </RunSectionNavProvider>
  )
}
