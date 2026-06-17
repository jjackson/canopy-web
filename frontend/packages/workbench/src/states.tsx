import type { JSX, ReactNode } from 'react'

export function LoadingSpinner({ label = 'Loading…' }: { label?: string }): JSX.Element {
  return (
    <div className="flex items-center gap-3 p-6 text-muted-foreground">
      <div className="h-4 w-4 animate-spin rounded-full border-2 border-muted-foreground/30 border-t-muted-foreground" />
      <span>{label}</span>
    </div>
  )
}

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string
  description?: string
  action?: ReactNode
}): JSX.Element {
  return (
    <div className="flex flex-col items-center justify-center gap-2 p-12 text-center">
      <h3 className="text-lg font-semibold text-muted-foreground">{title}</h3>
      {description && <p className="text-sm text-muted-foreground">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  )
}

export function ErrorState({
  title = 'Something went wrong',
  message,
  onRetry,
}: {
  title?: string
  message: string
  onRetry?: () => void
}): JSX.Element {
  return (
    <div className="rounded border border-destructive/30 bg-destructive/10 p-4 text-sm text-destructive">
      <div className="font-semibold">{title}</div>
      <div className="mt-1">{message}</div>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="mt-3 rounded bg-destructive px-3 py-1 text-destructive-foreground hover:bg-destructive/90"
        >
          Retry
        </button>
      )}
    </div>
  )
}

/** Pulsing card placeholders while a section lazy-loads its data. */
export function WorkbenchSkeleton({ rows = 3 }: { rows?: number }): JSX.Element {
  return (
    <div className="animate-pulse space-y-3">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="rounded-xl border border-border bg-card p-5">
          <div className="mb-2 h-4 w-2/3 rounded bg-muted" />
          <div className="h-3 w-full rounded bg-muted/70" />
        </div>
      ))}
    </div>
  )
}
