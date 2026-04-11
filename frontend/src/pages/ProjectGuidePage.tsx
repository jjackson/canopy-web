import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { projectsApi, type ProjectGuide } from '@/api/projects'

export function ProjectGuidePage() {
  const { slug } = useParams<{ slug: string }>()
  const [guide, setGuide] = useState<ProjectGuide | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!slug) return
    let cancelled = false
    setLoading(true)
    void (async () => {
      try {
        const data = await projectsApi.getGuide(slug)
        if (!cancelled) setGuide(data)
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Failed to load guide')
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => { cancelled = true }
  }, [slug])

  if (loading) return <div className="text-stone-600 text-sm">Loading...</div>
  if (error) {
    return (
      <div>
        <Link to="/" className="text-orange-400/70 hover:text-orange-400 text-xs">← Back to projects</Link>
        <div className="mt-6 text-stone-500 text-sm">No guide found for this project yet.</div>
      </div>
    )
  }
  if (!guide) return null

  return (
    <div className="max-w-3xl mx-auto">
      <Link to="/" className="text-orange-400/70 hover:text-orange-400 text-xs">← Back to projects</Link>
      <h1 className="text-2xl font-bold text-stone-100 mt-4 mb-2">{slug}</h1>
      <div className="text-[11px] text-stone-700 mb-8">
        Guide · {guide.source} · Updated {new Date(guide.updated_at).toLocaleDateString()}
      </div>
      <pre className="text-sm text-stone-300 leading-relaxed whitespace-pre-wrap font-sans">{guide.content}</pre>
    </div>
  )
}
