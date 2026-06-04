import { DddLeftNav } from '@/components/ddd/DddLeftNav'
import { ReviewsPage } from './ReviewsPage'

/**
 * The DDD Plans view: the same persistent left nav as the rest of the DDD
 * section (narratives → runs, plus the Plans link), with the reviews/plans
 * table in the wide main area. Lives under /ddd-plans so Plans is reached
 * from within DDD rather than as a separate top-level nav item.
 */
export function DddPlansPage() {
  return (
    <div className="flex h-full">
      <DddLeftNav />
      <main className="flex-1 overflow-y-auto px-6 py-8">
        <ReviewsPage />
      </main>
    </div>
  )
}
