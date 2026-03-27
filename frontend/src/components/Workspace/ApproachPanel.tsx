import { StreamingText } from './StreamingText'

interface Step {
  name?: string
  description?: string
  tools?: string[]
}

interface Approach {
  name?: string
  description?: string
  steps?: Step[]
}

interface ApproachPanelProps {
  approach: Approach | null
  streamingText: string
  isStreaming: boolean
}

export function ApproachPanel({ approach, streamingText, isStreaming }: ApproachPanelProps) {
  // During analysis — show streaming text
  if (!approach && (isStreaming || streamingText)) {
    return (
      <div className="p-4">
        <h3 className="mb-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">
          Analyzing sources...
        </h3>
        <StreamingText text={streamingText} isStreaming={isStreaming} />
      </div>
    )
  }

  // No approach yet and not streaming
  if (!approach) {
    return (
      <div className="p-4 text-sm text-gray-400">
        Waiting for AI to propose an approach...
      </div>
    )
  }

  // Structured approach display
  const steps = approach.steps ?? []

  return (
    <div className="p-4 space-y-4">
      <div>
        <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wide">
          Proposed Skill
        </h3>
        <p className="mt-1 text-base font-semibold text-gray-900">
          {approach.name ?? 'Untitled Skill'}
        </p>
        {approach.description && (
          <p className="mt-1 text-sm text-gray-600">{approach.description}</p>
        )}
      </div>

      {steps.length > 0 && (
        <div>
          <h4 className="mb-2 text-xs font-semibold text-gray-500 uppercase tracking-wide">
            Steps ({steps.length})
          </h4>
          <div className="space-y-2">
            {steps.map((step, i) => (
              <div
                key={step.name ?? i}
                className="rounded border border-gray-200 p-3"
              >
                <p className="text-sm font-medium text-gray-900">
                  {i + 1}. {step.name ?? 'Unnamed step'}
                </p>
                {step.description && (
                  <p className="mt-1 text-xs text-gray-600">{step.description}</p>
                )}
                {step.tools && step.tools.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1">
                    {step.tools.map((tool) => (
                      <span
                        key={tool}
                        className="rounded bg-gray-100 px-1.5 py-0.5 text-xs text-gray-600 font-mono"
                      >
                        {tool}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
