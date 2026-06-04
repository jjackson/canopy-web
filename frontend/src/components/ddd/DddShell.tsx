import type { ReactNode } from 'react'
import { DddLeftNav } from './DddLeftNav'

/**
 * The DDD section chrome: the persistent left rail (narratives → versions →
 * runs) plus a wide scrolling main area. Every DDD screen — narrative landing,
 * run package, and the narrative editor — renders inside this so the rail
 * stays put and highlights wherever you are.
 *
 * Assumes a full-bleed parent (AppLayout renders /ddd and /review at full
 * viewport height); the main area owns its own scroll.
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
    <div className="flex h-full">
      <DddLeftNav activeSlug={activeSlug} activeRunId={activeRunId} />
      <main className="flex-1 overflow-y-auto">{children}</main>
    </div>
  )
}
