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
      <div className="p-5">
        <h3 className="mb-3 text-[10px] font-semibold text-stone-500 uppercase tracking-wider">
          Analyzing sources...
        </h3>
        <div className="rounded-lg border border-stone-800 bg-stone-950 border-l-2 border-l-orange-400 p-3">
          <StreamingText text={streamingText} isStreaming={isStreaming} />
        </div>
      </div>
    )
  }

  // No approach yet and not streaming
  if (!approach) {
    return (
      <div className="p-5 text-sm text-stone-500 italic">
        Waiting for AI to propose an approach...
      </div>
    )
  }

  // Structured approach display
  const steps = approach.steps ?? []

  return (
    <div className="p-5 space-y-6">
      <div>
        <h3 className="text-[10px] font-semibold text-stone-500 uppercase tracking-wider">
          Proposed Skill
        </h3>
        <p className="mt-1.5 text-base font-semibold text-stone-100">
          {approach.name ?? 'Untitled Skill'}
        </p>
        {approach.description && (
          <p className="mt-1 text-sm text-stone-400 leading-relaxed">{approach.description}</p>
        )}
      </div>

      {steps.length > 0 && (
        <div>
          <h4 className="mb-2 text-[10px] font-semibold text-stone-500 uppercase tracking-wider">
            Steps ({steps.length})
          </h4>
          <div className="space-y-2">
            {steps.map((step, i) => (
              <div
                key={step.name ?? i}
                className="rounded-lg border border-stone-800 bg-stone-950 p-3 hover:border-stone-700 transition-colors"
              >
                <p className="text-sm font-medium text-stone-100">
                  <span className="text-stone-600 mr-1.5">{i + 1}.</span>
                  {step.name ?? 'Unnamed step'}
                </p>
                {step.description && (
                  <p className="mt-1 text-xs text-stone-400 leading-relaxed">{step.description}</p>
                )}
                {step.tools && step.tools.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1">
                    {step.tools.map((tool) => (
                      <span
                        key={tool}
                        className="rounded bg-stone-900 border border-stone-800 px-1.5 py-0.5 text-[10px] text-stone-400 font-mono"
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
