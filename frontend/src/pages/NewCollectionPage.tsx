import { useState, useCallback } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { api } from '@/api/client'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Badge } from '@/components/ui/badge'

const SOURCE_TYPES = ['transcript', 'slack', 'document', 'text'] as const
type SourceType = (typeof SOURCE_TYPES)[number]

const TYPE_PLACEHOLDERS: Record<SourceType, string> = {
  transcript: 'e.g., Customer onboarding call',
  slack: 'e.g., #eng-support thread',
  document: 'e.g., Runbook: deploy process',
  text: 'e.g., Notes on incident response',
}

type Source = {
  id: number
  source_type: SourceType
  title: string
  content: string
}

type CollectionResult = { id: number }

export function NewCollectionPage() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const reviseSkillId = searchParams.get('revise')
    ? Number(searchParams.get('revise'))
    : null

  // Step tracking: 'name' | 'sources' | 'analysis'
  const [step, setStep] = useState<'name' | 'sources' | 'analysis'>('name')

  // Step 1: Collection info
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')

  // Collection state (set after creation)
  const [collectionId, setCollectionId] = useState<number | null>(null)

  // Step 2: Sources
  const [sources, setSources] = useState<Source[]>([])
  const [sourceType, setSourceType] = useState<SourceType>('transcript')
  const [sourceTitle, setSourceTitle] = useState('')
  const [sourceContent, setSourceContent] = useState('')
  const [addingSource, setAddingSource] = useState(false)
  const [deletingSourceId, setDeletingSourceId] = useState<number | null>(null)

  // Step 3: Analysis
  const [analysisStatus, setAnalysisStatus] = useState<string | null>(null)

  // Shared
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  // Step 1 → Step 2: Create collection, then move to sources step
  const handleCreateCollection = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault()
      const trimmedName = name.trim()
      if (!trimmedName) {
        setError('Please enter a collection name.')
        return
      }

      setError(null)
      setSubmitting(true)

      try {
        const collection = (await api.createCollection(
          trimmedName,
          description.trim()
        )) as CollectionResult
        setCollectionId(collection.id)
        setStep('sources')
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to create collection.')
      } finally {
        setSubmitting(false)
      }
    },
    [name, description]
  )

  // Add a source to the collection via API
  const handleAddSource = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault()
      if (collectionId == null) return

      const trimmedContent = sourceContent.trim()
      if (!trimmedContent) {
        setError('Please paste source content.')
        return
      }

      setError(null)
      setAddingSource(true)

      try {
        const result = (await api.addSource(collectionId, {
          source_type: sourceType,
          title: sourceTitle.trim() || undefined,
          content: trimmedContent,
        })) as Source

        setSources((prev) => [...prev, result])
        // Reset the add-source form
        setSourceTitle('')
        setSourceContent('')
        setSourceType('transcript')
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to add source.')
      } finally {
        setAddingSource(false)
      }
    },
    [collectionId, sourceType, sourceTitle, sourceContent]
  )

  // Delete a source (optimistic removal from local list)
  const handleDeleteSource = useCallback(
    (sourceId: number) => {
      setDeletingSourceId(sourceId)
      setSources((prev) => prev.filter((s) => s.id !== sourceId))
      setDeletingSourceId(null)
    },
    []
  )

  // Step 2 → Step 3: Start analysis
  const handleStartAnalysis = useCallback(async () => {
    if (collectionId == null || sources.length === 0) return

    setError(null)
    setSubmitting(true)
    setStep('analysis')

    try {
      setAnalysisStatus('Analyzing sources (this may take 30-60 seconds)...')
      const result = await api.analyzeWorkspace(collectionId)
      navigate(`/workspace/${result.session_id}${reviseSkillId ? `?revise=${reviseSkillId}` : ''}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Analysis failed.')
      setSubmitting(false)
      setStep('sources')
      setAnalysisStatus(null)
    }
  }, [collectionId, sources.length, navigate, reviseSkillId])

  // First line of content for preview
  function firstLine(content: string, maxLen = 80): string {
    const line = content.split('\n')[0] || ''
    return line.length > maxLen ? line.slice(0, maxLen) + '...' : line
  }

  // Step label for subtle progress indicator
  const stepLabels = [
    { id: 'name', label: 'Name' },
    { id: 'sources', label: 'Sources' },
    { id: 'analysis', label: 'Analyze' },
  ] as const

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      {/* Header */}
      <div>
        <div className="flex items-center gap-3">
          <h1 className="text-lg font-semibold text-stone-100">
            {reviseSkillId ? `Revising: Skill #${reviseSkillId}` : 'New Skill from Sources'}
          </h1>
        </div>
        <p className="mt-1 text-sm text-stone-500">
          {step === 'name' && 'Name your collection, then add one or more sources for the AI to analyze.'}
          {step === 'sources' && 'Add conversations, documents, or transcripts. The AI will analyze all sources together.'}
          {step === 'analysis' && 'The AI is analyzing your sources...'}
        </p>

        {/* Subtle step indicator */}
        <div className="mt-4 flex items-center gap-2">
          {stepLabels.map((s, i) => {
            const currentIdx = stepLabels.findIndex((x) => x.id === step)
            const active = i === currentIdx
            const done = i < currentIdx
            return (
              <div key={s.id} className="flex items-center gap-2">
                {i > 0 && (
                  <span className={`h-px w-6 ${done ? 'bg-orange-400/50' : 'bg-stone-800'}`} />
                )}
                <span
                  className={`text-[10px] uppercase tracking-wider font-semibold ${
                    active
                      ? 'text-orange-400'
                      : done
                        ? 'text-stone-400'
                        : 'text-stone-600'
                  }`}
                >
                  {s.label}
                </span>
              </div>
            )
          })}
        </div>
      </div>

      {/* Error banner */}
      {error && (
        <div className="rounded-lg border border-red-400/30 bg-red-400/10 p-3 text-sm text-red-400">
          {error}
        </div>
      )}

      {/* Step 1: Name the collection */}
      {step === 'name' && (
        <form onSubmit={(e) => void handleCreateCollection(e)} className="space-y-4 rounded-xl border border-stone-800 bg-stone-900 p-6">
          <div>
            <label htmlFor="collection-name" className="mb-1.5 block text-[10px] uppercase tracking-wider font-semibold text-stone-500">
              Collection Name
            </label>
            <Input
              id="collection-name"
              placeholder="e.g., Customer Onboarding Flow"
              value={name}
              onChange={(e) => setName(e.target.value)}
              disabled={submitting}
            />
          </div>

          <div>
            <label htmlFor="collection-description" className="mb-1.5 block text-[10px] uppercase tracking-wider font-semibold text-stone-500">
              Description <span className="text-stone-600 normal-case tracking-normal">(optional)</span>
            </label>
            <Textarea
              id="collection-description"
              placeholder="Brief description of what this collection covers..."
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              disabled={submitting}
              className="min-h-[70px]"
            />
          </div>

          <div className="pt-1">
            <Button type="submit" disabled={submitting}>
              {submitting ? 'Creating...' : 'Next'}
            </Button>
          </div>
        </form>
      )}

      {/* Step 2: Add sources */}
      {step === 'sources' && (
        <div className="space-y-6">
          {/* Collection header */}
          <div className="rounded-xl border border-stone-800 bg-stone-900 px-4 py-3">
            <h2 className="text-sm font-semibold text-stone-100">{name}</h2>
            {description && (
              <p className="mt-0.5 text-xs text-stone-500">{description}</p>
            )}
          </div>

          {/* Source list */}
          {sources.length > 0 && (
            <div className="space-y-2">
              {sources.map((source) => (
                <div
                  key={source.id}
                  className="flex items-start gap-3 rounded-lg border border-stone-800 bg-stone-900 px-3 py-2.5 hover:border-stone-700 transition-colors"
                >
                  <Badge variant="secondary" className="mt-0.5 shrink-0">
                    {source.source_type}
                  </Badge>
                  <div className="min-w-0 flex-1">
                    {source.title && (
                      <div className="text-sm font-medium text-stone-200">{source.title}</div>
                    )}
                    <div className="truncate text-xs text-stone-500">
                      {firstLine(source.content)}
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => handleDeleteSource(source.id)}
                    disabled={deletingSourceId === source.id}
                    className="shrink-0 text-sm text-stone-600 hover:text-red-400 transition-colors"
                    title="Remove source"
                  >
                    &times;
                  </button>
                </div>
              ))}
            </div>
          )}

          {/* Source count */}
          <div className="text-[10px] uppercase tracking-wider font-semibold text-stone-500">
            {sources.length === 0
              ? 'No sources added yet'
              : `${sources.length} source${sources.length === 1 ? '' : 's'} added`}
          </div>

          {/* Add source form */}
          <form onSubmit={(e) => void handleAddSource(e)} className="space-y-3 rounded-xl border border-stone-800 bg-stone-900 p-4">
            <div className="text-[10px] uppercase tracking-wider font-semibold text-stone-500">Add Source</div>

            <div className="flex gap-3">
              <div className="w-36">
                <label htmlFor="source-type" className="mb-1 block text-[10px] uppercase tracking-wider text-stone-500">
                  Type
                </label>
                <select
                  id="source-type"
                  value={sourceType}
                  onChange={(e) => setSourceType(e.target.value as SourceType)}
                  disabled={addingSource}
                  className="h-8 w-full rounded-lg border border-stone-700 bg-stone-950 px-2 text-sm text-stone-200 focus:border-orange-400/50 focus:outline-none focus:ring-2 focus:ring-orange-400/20"
                >
                  {SOURCE_TYPES.map((t) => (
                    <option key={t} value={t} className="bg-stone-900 text-stone-200">
                      {t}
                    </option>
                  ))}
                </select>
              </div>

              <div className="flex-1">
                <label htmlFor="source-title" className="mb-1 block text-[10px] uppercase tracking-wider text-stone-500">
                  Title <span className="text-stone-600 normal-case tracking-normal">(optional)</span>
                </label>
                <Input
                  id="source-title"
                  placeholder={TYPE_PLACEHOLDERS[sourceType]}
                  value={sourceTitle}
                  onChange={(e) => setSourceTitle(e.target.value)}
                  disabled={addingSource}
                />
              </div>
            </div>

            <div>
              <label htmlFor="source-content" className="mb-1 block text-[10px] uppercase tracking-wider text-stone-500">
                Content
              </label>
              <Textarea
                id="source-content"
                placeholder="Paste content here..."
                value={sourceContent}
                onChange={(e) => setSourceContent(e.target.value)}
                disabled={addingSource}
                className="min-h-[200px] font-mono text-xs"
              />
            </div>

            <Button type="submit" variant="secondary" disabled={addingSource || !sourceContent.trim()}>
              {addingSource ? 'Adding...' : 'Add'}
            </Button>
          </form>

          {/* Start Analysis */}
          <div className="flex items-center gap-3 border-t border-stone-800 pt-4">
            <Button
              onClick={() => void handleStartAnalysis()}
              disabled={sources.length === 0 || submitting}
            >
              Start Analysis
            </Button>
            {sources.length === 0 && (
              <span className="text-xs text-stone-500">Add at least 1 source to continue</span>
            )}
          </div>
        </div>
      )}

      {/* Step 3: Analysis in progress */}
      {step === 'analysis' && (
        <div className="rounded-xl border border-stone-800 bg-stone-900 p-6 space-y-4">
          <div className="flex items-center gap-3">
            <div className="h-4 w-4 animate-spin rounded-full border-2 border-stone-700 border-t-orange-400" />
            <span className="text-sm text-stone-300">{analysisStatus}</span>
          </div>
        </div>
      )}
    </div>
  )
}
