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
                  isCompleted ? 'bg-primary/40' : 'bg-muted'
                )}
              />
            )}
            <span
              className={cn(
                'rounded px-2 py-0.5 text-[10px] uppercase tracking-wider font-semibold transition-colors',
                isCurrent && 'bg-primary/10 border border-primary/30 text-primary',
                isCompleted && 'text-foreground-secondary bg-card border border-border',
                !isCurrent && !isCompleted && 'text-muted-foreground'
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
