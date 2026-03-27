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
        'flex flex-col border-r border-gray-200 bg-white transition-all',
        collapsed ? 'w-12' : 'w-full'
      )}
    >
      <button
        type="button"
        onClick={() => setCollapsed(!collapsed)}
        className="flex items-center gap-2 border-b border-gray-200 px-3 py-2 text-left text-xs font-semibold text-gray-700 hover:bg-gray-50"
      >
        <span
          className={cn(
            'text-gray-400 transition-transform',
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
            <p className="text-xs text-gray-400">No sources loaded.</p>
          )}
          {sources.map((source, i) => (
            <div
              key={source.id ?? i}
              className="rounded border border-gray-200 p-2"
            >
              <div className="mb-1 flex items-center gap-2">
                {source.source_type && (
                  <Badge variant="secondary">{source.source_type}</Badge>
                )}
                {source.title && (
                  <span className="truncate text-xs font-medium text-gray-700">
                    {source.title}
                  </span>
                )}
              </div>
              <div className="max-h-40 overflow-y-auto text-xs text-gray-600 whitespace-pre-wrap font-mono leading-relaxed">
                {source.content ?? '(empty)'}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
