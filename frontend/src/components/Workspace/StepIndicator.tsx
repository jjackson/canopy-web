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
                  'mx-1 h-px w-4',
                  isCompleted ? 'bg-gray-400' : 'bg-gray-200'
                )}
              />
            )}
            <span
              className={cn(
                'rounded px-2 py-0.5 text-xs font-medium',
                isCurrent && 'bg-gray-900 text-white',
                isCompleted && 'text-gray-500 bg-gray-200',
                !isCurrent && !isCompleted && 'text-gray-400'
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
