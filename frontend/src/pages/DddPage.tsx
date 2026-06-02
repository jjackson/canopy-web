import { useParams } from 'react-router-dom'
import { DddLeftNav } from '@/components/ddd/DddLeftNav'
import { NarrativeLanding } from '@/components/ddd/NarrativeLanding'
import { RunPackage } from '@/components/ddd/RunPackage'

/**
 * The DDD section: a persistent left nav (narratives → runs) plus a wide main
 * area that shows either a narrative landing or a single run's package,
 * switched by the URL params.
 *   /ddd                    → pick a narrative
 *   /ddd/:narrative         → narrative landing (story + runs)
 *   /ddd/:narrative/:runId  → run package
 */
export function DddPage() {
  const { narrative, runId } = useParams<{ narrative?: string; runId?: string }>()

  return (
    <div className="flex h-full">
      <DddLeftNav activeSlug={narrative} activeRunId={runId} />
      <main className="flex-1 overflow-y-auto">
        {runId ? (
          <RunPackage key={runId} runId={runId} />
        ) : narrative ? (
          <NarrativeLanding key={narrative} slug={narrative} />
        ) : (
          <div className="flex h-full items-center justify-center text-sm text-stone-600">
            Select a narrative to see its runs.
          </div>
        )}
      </main>
    </div>
  )
}
