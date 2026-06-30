import { useState } from 'react'
import { cn } from '@/lib/utils'
import { Badge } from '@marshellis/canopy-ui/ui'

interface Source {
  id?: number
  source_type?: string
  title?: string
  content?: string
}

interface SourcePanelProps {
  sources: Source[]
}

export function SourcePanel({ sources }: SourcePanelProps) {
  const [collapsed, setCollapsed] = useState(false)

  return (
    <div
      className={cn(
        'flex flex-col h-full bg-background transition-all',
        collapsed ? 'w-12' : 'w-full'
      )}
    >
      <button
        type="button"
        onClick={() => setCollapsed(!collapsed)}
        className="flex items-center gap-2 border-b border-border px-3 py-2.5 text-left text-[10px] uppercase tracking-wider font-semibold text-muted-foreground hover:text-foreground-secondary hover:bg-card/50 transition-colors"
      >
        <span
          className={cn(
            'text-muted-foreground transition-transform',
            collapsed && '-rotate-90'
          )}
        >
          &#9660;
        </span>
        {!collapsed && <span>Sources ({sources.length})</span>}
      </button>

      {!collapsed && (
        <div className="flex-1 overflow-y-auto p-3 space-y-2">
          {sources.length === 0 && (
            <p className="text-xs text-muted-foreground italic">No sources loaded.</p>
          )}
          {sources.map((source, i) => (
            <div
              key={source.id ?? i}
              className="rounded-lg border border-border bg-card p-3"
            >
              <div className="mb-2 flex items-center gap-2">
                {source.source_type && (
                  <Badge variant="secondary">{source.source_type}</Badge>
                )}
                {source.title && (
                  <span className="truncate text-xs font-medium text-foreground-secondary">
                    {source.title}
                  </span>
                )}
              </div>
              <div className="max-h-40 overflow-y-auto text-xs text-muted-foreground whitespace-pre-wrap font-mono leading-relaxed border-l-2 border-border pl-2">
                {source.content ?? '(empty)'}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
