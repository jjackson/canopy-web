import { useEffect, useState } from 'react'
import { type Project, projectsApi } from '@/api/projects'

function DeployBadge({ url }: { url: string }) {
  if (!url) return <span className="text-[10px] text-stone-600">—</span>
  const hostname = (() => {
    try { return new URL(url).hostname.replace('www.', '') } catch { return url }
  })()
  return (
    <a href={url} target="_blank" rel="noopener noreferrer"
      className="inline-flex items-center gap-1.5 text-[10px] bg-stone-800 text-stone-400 px-2 py-0.5 rounded hover:text-stone-200 transition-colors"
      onClick={(e) => e.stopPropagation()}>
      <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 shadow-[0_0_4px_rgba(74,222,128,0.4)]" />
      {hostname}
    </a>
  )
}

function StatusDot({ status }: { status: string }) {
  const color = status === 'active'
    ? 'bg-orange-400 shadow-[0_0_6px_rgba(251,146,60,0.3)]'
    : status === 'stale'
      ? 'bg-stone-500'
      : 'bg-stone-700'
  return <span className={`w-[7px] h-[7px] rounded-full shrink-0 ${color}`} />
}

function ContextLine({ label, text, muted }: { label: string; text?: string; muted?: boolean }) {
  if (!text) return null
  return (
    <div className={`text-xs leading-relaxed ${muted ? 'text-stone-600' : 'text-stone-400'}`}>
      <span className="text-stone-600 uppercase text-[9px] tracking-wide font-medium mr-2">{label}</span>
      {text}
    </div>
  )
}

function ProjectTile({ project, onContextSaved }: { project: Project; onContextSaved: () => void }) {
  const [expanded, setExpanded] = useState(false)
  const [editType, setEditType] = useState<string | null>(null)
  const [editValue, setEditValue] = useState('')
  const [saving, setSaving] = useState(false)

  const ctx = project.latest_context || {}

  async function saveContext() {
    if (!editType || !editValue.trim()) return
    setSaving(true)
    try {
      await projectsApi.postContext(project.slug, {
        context_type: editType,
        content: editValue.trim(),
        source: 'jonathan',
      })
      setEditType(null)
      setEditValue('')
      onContextSaved()
    } finally {
      setSaving(false)
    }
  }

  return (
    <div
      className={`bg-stone-900 border rounded-lg cursor-pointer transition-colors ${
        expanded ? 'border-stone-700' : 'border-stone-800 hover:border-stone-700'
      }`}
      onClick={() => setExpanded(!expanded)}
    >
      <div className="p-4">
        <div className="flex items-center gap-3 mb-2">
          <StatusDot status={project.status} />
          <span className="text-sm font-semibold text-stone-100">{project.name}</span>
          <div className="ml-auto flex items-center gap-2">
            {project.visibility === 'private' && (
              <span className="text-[9px] text-stone-500 border border-orange-400/15 bg-orange-400/5 px-1.5 py-0.5 rounded uppercase tracking-wide">private</span>
            )}
            <DeployBadge url={project.deploy_url} />
          </div>
        </div>
        <ContextLine label="now" text={ctx.current_work?.content} />
        <ContextLine label="next" text={ctx.next_step?.content} muted />
        {!ctx.current_work && !ctx.next_step && (
          <div className="text-xs text-stone-700 italic">No context yet</div>
        )}
      </div>

      {expanded && (
        <div className="border-t border-stone-800 px-4 pb-4 pt-3" onClick={(e) => e.stopPropagation()}>
          <div className="flex gap-4 mb-3 text-[11px]">
            {project.repo_url && (
              <a href={project.repo_url} target="_blank" rel="noopener noreferrer"
                className="text-orange-400/70 hover:text-orange-400 transition-colors">
                GitHub ↗
              </a>
            )}
            {project.deploy_url && (
              <a href={project.deploy_url} target="_blank" rel="noopener noreferrer"
                className="text-orange-400/70 hover:text-orange-400 transition-colors">
                Live Site ↗
              </a>
            )}
          </div>

          {ctx.summary && (
            <div className="bg-stone-950 border-l-2 border-orange-400 rounded-r-lg p-3 mb-3 text-xs text-stone-400 leading-relaxed">
              {ctx.summary.content}
              <div className="text-[10px] text-stone-700 mt-1">
                {ctx.summary.source} · {new Date(ctx.summary.created_at).toLocaleDateString()}
              </div>
            </div>
          )}

          {editType ? (
            <div className="flex gap-2 mt-2">
              <input
                type="text"
                className="flex-1 bg-stone-950 border border-stone-700 rounded px-3 py-1.5 text-xs text-stone-200 placeholder:text-stone-600 focus:outline-none focus:border-orange-400/50"
                placeholder={`Update ${editType === 'current_work' ? 'current work' : 'next step'}...`}
                value={editValue}
                onChange={(e) => setEditValue(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') saveContext(); if (e.key === 'Escape') setEditType(null) }}
                autoFocus
              />
              <button onClick={saveContext} disabled={saving}
                className="text-xs px-3 py-1.5 rounded bg-orange-400/10 border border-orange-400/30 text-orange-400 hover:bg-orange-400/20 disabled:opacity-50 transition-colors">
                {saving ? '...' : 'Save'}
              </button>
            </div>
          ) : (
            <div className="flex gap-2 mt-2">
              <button onClick={() => setEditType('current_work')}
                className="text-[11px] px-2.5 py-1 rounded bg-stone-950 border border-stone-700 text-stone-500 hover:text-stone-300 hover:border-stone-600 transition-colors">
                Update current work
              </button>
              <button onClick={() => setEditType('next_step')}
                className="text-[11px] px-2.5 py-1 rounded bg-stone-950 border border-stone-700 text-stone-500 hover:text-stone-300 hover:border-stone-600 transition-colors">
                Update next step
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export function ProjectsPage() {
  const [projects, setProjects] = useState<Project[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [refreshKey, setRefreshKey] = useState(0)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    void (async () => {
      try {
        const data = await projectsApi.list()
        if (!cancelled) setProjects(data)
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Failed to load projects')
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => { cancelled = true }
  }, [refreshKey])

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64 text-stone-600 text-sm">
        Loading projects...
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex items-center justify-center h-64 text-red-400 text-sm">
        {error}
      </div>
    )
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-lg font-semibold text-stone-100">Projects</h1>
        <span className="text-xs text-stone-600 bg-stone-900 px-2.5 py-1 rounded">
          {projects.length} projects
        </span>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-2">
        {projects.map((project) => (
          <ProjectTile key={project.id} project={project} onContextSaved={() => setRefreshKey((k) => k + 1)} />
        ))}
      </div>
    </div>
  )
}
