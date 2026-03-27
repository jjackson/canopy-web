import { useState } from 'react'
import { cn } from '@/lib/utils'

interface EvalCase {
  name?: string
  input?: string
  expected_output?: string
}

interface EvalPanelProps {
  evalCases: EvalCase[]
}

export function EvalPanel({ evalCases }: EvalPanelProps) {
  const [collapsed, setCollapsed] = useState(false)

  return (
    <div className="border-t border-gray-200">
      <button
        type="button"
        onClick={() => setCollapsed(!collapsed)}
        className="flex w-full items-center gap-2 px-4 py-2 text-left text-xs font-semibold text-gray-700 hover:bg-gray-50"
      >
        <span
          className={cn(
            'text-gray-400 transition-transform',
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
            <p className="text-xs text-gray-400">
              No eval cases yet. The AI will propose cases after analyzing your sources.
            </p>
          )}
          {evalCases.map((ec, i) => (
            <div
              key={ec.name ?? i}
              className="rounded border border-gray-200 p-3"
            >
              <p className="text-sm font-medium text-gray-900">
                {ec.name ?? `Case ${i + 1}`}
              </p>
              {ec.input != null && (
                <div className="mt-2">
                  <span className="text-xs font-semibold text-gray-500">Input</span>
                  <pre className="mt-0.5 max-h-28 overflow-auto rounded bg-gray-50 p-2 text-xs text-gray-700 font-mono">
                    {ec.input}
                  </pre>
                </div>
              )}
              {ec.expected_output != null && (
                <div className="mt-2">
                  <span className="text-xs font-semibold text-gray-500">Expected Output</span>
                  <pre className="mt-0.5 max-h-28 overflow-auto rounded bg-gray-50 p-2 text-xs text-gray-700 font-mono">
                    {ec.expected_output}
                  </pre>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
