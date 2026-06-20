import { useState } from 'react'
import { cn } from '@/lib/utils'

interface EvalCase {
  name?: string
  input?: string | Record<string, unknown>
  expected?: string | Record<string, unknown>
  expected_output?: string | Record<string, unknown>
}

interface EvalPanelProps {
  evalCases: EvalCase[]
}

/** Render a value as displayable text — stringify objects, pass strings through */
function displayValue(value: unknown): string {
  if (value == null) return ''
  if (typeof value === 'string') return value
  return JSON.stringify(value, null, 2)
}

export function EvalPanel({ evalCases }: EvalPanelProps) {
  const [collapsed, setCollapsed] = useState(false)

  return (
    <div className="border-t border-border bg-background/50 max-h-64 overflow-y-auto">
      <button
        type="button"
        onClick={() => setCollapsed(!collapsed)}
        className="flex w-full items-center gap-2 px-4 py-2.5 text-left text-[10px] uppercase tracking-wider font-semibold text-muted-foreground hover:text-foreground-secondary hover:bg-card/50 transition-colors"
      >
        <span
          className={cn(
            'text-muted-foreground transition-transform',
            collapsed && '-rotate-90'
          )}
        >
          &#9660;
        </span>
        <span>Eval Cases ({evalCases.length})</span>
      </button>

      {!collapsed && (
        <div className="px-4 pb-4 space-y-2">
          {evalCases.length === 0 && (
            <p className="text-xs text-muted-foreground italic">
              No eval cases yet. The AI will propose cases after analyzing your sources.
            </p>
          )}
          {evalCases.map((ec, i) => {
            const expectedValue = ec.expected_output ?? ec.expected
            return (
              <div
                key={ec.name ?? i}
                className="rounded-lg border border-border bg-card p-3"
              >
                <p className="text-sm font-medium text-foreground">
                  {ec.name ?? `Case ${i + 1}`}
                </p>
                {ec.input != null && (
                  <div className="mt-2">
                    <span className="text-[10px] uppercase tracking-wider font-semibold text-muted-foreground">Input</span>
                    <pre className="mt-1 max-h-28 overflow-auto rounded border border-border bg-background p-2 text-xs text-foreground-secondary font-mono">
                      {displayValue(ec.input)}
                    </pre>
                  </div>
                )}
                {expectedValue != null && (
                  <div className="mt-2">
                    <span className="text-[10px] uppercase tracking-wider font-semibold text-muted-foreground">Expected Output</span>
                    <pre className="mt-1 max-h-28 overflow-auto rounded border border-border bg-background p-2 text-xs text-foreground-secondary font-mono">
                      {displayValue(expectedValue)}
                    </pre>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
