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

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-lg font-semibold text-gray-900">
          {reviseSkillId ? `Revising: Skill #${reviseSkillId}` : 'New Skill from Sources'}
        </h1>
        <p className="mt-1 text-sm text-gray-500">
          {step === 'name' && 'Name your collection, then add one or more sources for the AI to analyze.'}
          {step === 'sources' && 'Add conversations, documents, or transcripts. The AI will analyze all sources together.'}
          {step === 'analysis' && 'The AI is analyzing your sources...'}
        </p>
      </div>

      {/* Error banner */}
      {error && (
        <div className="rounded border border-red-200 bg-red-50 p-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {/* Step 1: Name the collection */}
      {step === 'name' && (
        <form onSubmit={(e) => void handleCreateCollection(e)} className="space-y-4">
          <div>
            <label htmlFor="collection-name" className="mb-1 block text-sm font-medium text-gray-700">
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
            <label htmlFor="collection-description" className="mb-1 block text-sm font-medium text-gray-700">
              Description <span className="text-gray-400">(optional)</span>
            </label>
            <Textarea
              id="collection-description"
              placeholder="Brief description of what this collection covers..."
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              disabled={submitting}
              className="min-h-[60px]"
            />
          </div>

          <Button type="submit" disabled={submitting}>
            {submitting ? 'Creating...' : 'Next'}
          </Button>
        </form>
      )}

      {/* Step 2: Add sources */}
      {step === 'sources' && (
        <div className="space-y-6">
          {/* Collection header */}
          <div className="flex items-center gap-2">
            <h2 className="text-base font-medium text-gray-900">{name}</h2>
            {description && (
              <span className="text-sm text-gray-500">— {description}</span>
            )}
          </div>

          {/* Source list */}
          {sources.length > 0 && (
            <div className="space-y-2">
              {sources.map((source) => (
                <div
                  key={source.id}
                  className="flex items-start gap-3 rounded border border-gray-200 bg-gray-50 px-3 py-2"
                >
                  <Badge variant="secondary" className="mt-0.5 shrink-0">
                    {source.source_type}
                  </Badge>
                  <div className="min-w-0 flex-1">
                    {source.title && (
                      <div className="text-sm font-medium text-gray-800">{source.title}</div>
                    )}
                    <div className="truncate text-sm text-gray-500">
                      {firstLine(source.content)}
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => handleDeleteSource(source.id)}
                    disabled={deletingSourceId === source.id}
                    className="shrink-0 text-sm text-gray-400 hover:text-red-500"
                    title="Remove source"
                  >
                    &times;
                  </button>
                </div>
              ))}
            </div>
          )}

          {/* Source count */}
          <div className="text-sm text-gray-500">
            {sources.length === 0
              ? 'No sources added yet'
              : `${sources.length} source${sources.length === 1 ? '' : 's'} added`}
          </div>

          {/* Add source form */}
          <form onSubmit={(e) => void handleAddSource(e)} className="space-y-3 rounded border border-gray-200 bg-white p-4">
            <div className="text-sm font-medium text-gray-700">Add Source</div>

            <div className="flex gap-3">
              <div className="w-36">
                <label htmlFor="source-type" className="mb-1 block text-xs text-gray-500">
                  Type
                </label>
                <select
                  id="source-type"
                  value={sourceType}
                  onChange={(e) => setSourceType(e.target.value as SourceType)}
                  disabled={addingSource}
                  className="h-8 w-full rounded-lg border border-gray-300 bg-white px-2 text-sm text-gray-700 focus:border-gray-400 focus:outline-none"
                >
                  {SOURCE_TYPES.map((t) => (
                    <option key={t} value={t}>
                      {t}
                    </option>
                  ))}
                </select>
              </div>

              <div className="flex-1">
                <label htmlFor="source-title" className="mb-1 block text-xs text-gray-500">
                  Title <span className="text-gray-400">(optional)</span>
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
              <label htmlFor="source-content" className="mb-1 block text-xs text-gray-500">
                Content
              </label>
              <Textarea
                id="source-content"
                placeholder="Paste content here..."
                value={sourceContent}
                onChange={(e) => setSourceContent(e.target.value)}
                disabled={addingSource}
                className="min-h-[200px]"
              />
            </div>

            <Button type="submit" variant="secondary" disabled={addingSource || !sourceContent.trim()}>
              {addingSource ? 'Adding...' : 'Add'}
            </Button>
          </form>

          {/* Start Analysis */}
          <div className="flex items-center gap-3 border-t border-gray-200 pt-4">
            <Button
              onClick={() => void handleStartAnalysis()}
              disabled={sources.length === 0 || submitting}
            >
              Start Analysis
            </Button>
            {sources.length === 0 && (
              <span className="text-sm text-gray-400">Add at least 1 source to continue</span>
            )}
          </div>
        </div>
      )}

      {/* Step 3: Analysis in progress */}
      {step === 'analysis' && (
        <div className="space-y-4">
          <div className="flex items-center gap-3">
            <div className="h-4 w-4 animate-spin rounded-full border-2 border-gray-300 border-t-gray-600" />
            <span className="text-sm text-gray-600">{analysisStatus}</span>
          </div>
        </div>
      )}
    </div>
  )
}
