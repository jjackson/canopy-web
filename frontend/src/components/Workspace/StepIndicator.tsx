import { cn } from '@/lib/utils'

const STEPS = ['Ingest', 'Review Approach', 'Edit', 'Test', 'Publish'] as const

interface StepIndicatorProps {
  currentStep: number
}

export function StepIndicator({ currentStep }: StepIndicatorProps) {
  return (
    <nav className="flex items-center gap-1">
      {STEPS.map((label, index) => {
        const isCompleted = index < currentStep
        const isCurrent = index === currentStep
        return (
          <div key={label} className="flex items-center gap-1">
            {index > 0 && (
              <span
                className={cn(
                  'mx-1 h-px w-5',
                  isCompleted ? 'bg-orange-400/40' : 'bg-stone-800'
                )}
              />
            )}
            <span
              className={cn(
                'rounded px-2 py-0.5 text-[10px] uppercase tracking-wider font-semibold transition-colors',
                isCurrent && 'bg-orange-400/10 border border-orange-400/30 text-orange-400',
                isCompleted && 'text-stone-400 bg-stone-900 border border-stone-800',
                !isCurrent && !isCompleted && 'text-stone-600'
              )}
            >
              {label}
            </span>
          </div>
        )
      })}
    </nav>
  )
}
