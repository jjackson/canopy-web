import { cn } from '@/lib/utils'

interface StreamingTextProps {
  text: string
  isStreaming: boolean
  className?: string
}

export function StreamingText({ text, isStreaming, className }: StreamingTextProps) {
  return (
    <div
      className={cn(
        'font-mono text-sm whitespace-pre-wrap leading-relaxed',
        className
      )}
    >
      {text}
      {isStreaming && (
        <span className="ml-0.5 inline-block h-4 w-1.5 animate-pulse bg-gray-900" />
      )}
    </div>
  )
}
