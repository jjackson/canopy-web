import { useState } from 'react'
import { cn } from '@/lib/utils'
import { Badge } from '@/components/ui/badge'

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
        'flex flex-col h-full bg-stone-950 transition-all',
        collapsed ? 'w-12' : 'w-full'
      )}
    >
      <button
        type="button"
        onClick={() => setCollapsed(!collapsed)}
        className="flex items-center gap-2 border-b border-stone-800 px-3 py-2.5 text-left text-[10px] uppercase tracking-wider font-semibold text-stone-500 hover:text-stone-300 hover:bg-stone-900/50 transition-colors"
      >
        <span
          className={cn(
            'text-stone-600 transition-transform',
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
            <p className="text-xs text-stone-600 italic">No sources loaded.</p>
          )}
          {sources.map((source, i) => (
            <div
              key={source.id ?? i}
              className="rounded-lg border border-stone-800 bg-stone-900 p-3"
            >
              <div className="mb-2 flex items-center gap-2">
                {source.source_type && (
                  <Badge variant="secondary">{source.source_type}</Badge>
                )}
                {source.title && (
                  <span className="truncate text-xs font-medium text-stone-300">
                    {source.title}
                  </span>
                )}
              </div>
              <div className="max-h-40 overflow-y-auto text-xs text-stone-500 whitespace-pre-wrap font-mono leading-relaxed border-l-2 border-stone-800 pl-2">
                {source.content ?? '(empty)'}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
