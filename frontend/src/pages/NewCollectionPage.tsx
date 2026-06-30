import { useState, useCallback } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { createCollection, addSource } from '@/api/collections'
import { Button } from '@marshellis/canopy-ui/ui'
import { Input } from '@marshellis/canopy-ui/ui'
import { Textarea } from '@marshellis/canopy-ui/ui'
import { Badge } from '@marshellis/canopy-ui/ui'

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

  // Step tracking: 'name' | 'sources'
  const [step, setStep] = useState<'name' | 'sources'>('name')

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
        const collection = (await createCollection(
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
        const result = (await addSource(collectionId, {
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

  // Step 2: Finish — collection + sources are saved; return to the workbench
  const handleFinish = useCallback(() => {
    if (collectionId == null) return
    navigate('/')
  }, [collectionId, navigate])

  // First line of content for preview
  function firstLine(content: string, maxLen = 80): string {
    const line = content.split('\n')[0] || ''
    return line.length > maxLen ? line.slice(0, maxLen) + '...' : line
  }

  // Step label for subtle progress indicator
  const stepLabels = [
    { id: 'name', label: 'Name' },
    { id: 'sources', label: 'Sources' },
  ] as const

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      {/* Header */}
      <div>
        <div className="flex items-center gap-3">
          <h1 className="text-lg font-semibold text-foreground">
            {reviseSkillId ? `Revising: Skill #${reviseSkillId}` : 'New Skill from Sources'}
          </h1>
        </div>
        <p className="mt-1 text-sm text-muted-foreground">
          {step === 'name' && 'Name your collection, then add one or more sources.'}
          {step === 'sources' && 'Add conversations, documents, or transcripts to this collection.'}
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
                  <span className={`h-px w-6 ${done ? 'bg-primary/50' : 'bg-muted'}`} />
                )}
                <span
                  className={`text-[10px] uppercase tracking-wider font-semibold ${
                    active
                      ? 'text-primary'
                      : done
                        ? 'text-foreground-secondary'
                        : 'text-muted-foreground'
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
        <div className="rounded-lg border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
          {error}
        </div>
      )}

      {/* Step 1: Name the collection */}
      {step === 'name' && (
        <form onSubmit={(e) => void handleCreateCollection(e)} className="space-y-4 rounded-xl border border-border bg-card p-6">
          <div>
            <label htmlFor="collection-name" className="mb-1.5 block text-[10px] uppercase tracking-wider font-semibold text-muted-foreground">
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
            <label htmlFor="collection-description" className="mb-1.5 block text-[10px] uppercase tracking-wider font-semibold text-muted-foreground">
              Description <span className="text-muted-foreground normal-case tracking-normal">(optional)</span>
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
          <div className="rounded-xl border border-border bg-card px-4 py-3">
            <h2 className="text-sm font-semibold text-foreground">{name}</h2>
            {description && (
              <p className="mt-0.5 text-xs text-muted-foreground">{description}</p>
            )}
          </div>

          {/* Source list */}
          {sources.length > 0 && (
            <div className="space-y-2">
              {sources.map((source) => (
                <div
                  key={source.id}
                  className="flex items-start gap-3 rounded-lg border border-border bg-card px-3 py-2.5 hover:border-input transition-colors"
                >
                  <Badge variant="secondary" className="mt-0.5 shrink-0">
                    {source.source_type}
                  </Badge>
                  <div className="min-w-0 flex-1">
                    {source.title && (
                      <div className="text-sm font-medium text-foreground-secondary">{source.title}</div>
                    )}
                    <div className="truncate text-xs text-muted-foreground">
                      {firstLine(source.content)}
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => handleDeleteSource(source.id)}
                    disabled={deletingSourceId === source.id}
                    className="shrink-0 text-sm text-muted-foreground hover:text-destructive transition-colors"
                    title="Remove source"
                  >
                    &times;
                  </button>
                </div>
              ))}
            </div>
          )}

          {/* Source count */}
          <div className="text-[10px] uppercase tracking-wider font-semibold text-muted-foreground">
            {sources.length === 0
              ? 'No sources added yet'
              : `${sources.length} source${sources.length === 1 ? '' : 's'} added`}
          </div>

          {/* Add source form */}
          <form onSubmit={(e) => void handleAddSource(e)} className="space-y-3 rounded-xl border border-border bg-card p-4">
            <div className="text-[10px] uppercase tracking-wider font-semibold text-muted-foreground">Add Source</div>

            <div className="flex gap-3">
              <div className="w-36">
                <label htmlFor="source-type" className="mb-1 block text-[10px] uppercase tracking-wider text-muted-foreground">
                  Type
                </label>
                <select
                  id="source-type"
                  value={sourceType}
                  onChange={(e) => setSourceType(e.target.value as SourceType)}
                  disabled={addingSource}
                  className="h-8 w-full rounded-lg border border-input bg-background px-2 text-sm text-foreground-secondary focus:border-primary/50 focus:outline-none focus:ring-2 focus:ring-primary/20"
                >
                  {SOURCE_TYPES.map((t) => (
                    <option key={t} value={t} className="bg-card text-foreground-secondary">
                      {t}
                    </option>
                  ))}
                </select>
              </div>

              <div className="flex-1">
                <label htmlFor="source-title" className="mb-1 block text-[10px] uppercase tracking-wider text-muted-foreground">
                  Title <span className="text-muted-foreground normal-case tracking-normal">(optional)</span>
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
              <label htmlFor="source-content" className="mb-1 block text-[10px] uppercase tracking-wider text-muted-foreground">
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

          {/* Finish */}
          <div className="flex items-center gap-3 border-t border-border pt-4">
            <Button
              onClick={() => handleFinish()}
              disabled={sources.length === 0 || submitting}
            >
              Done
            </Button>
            {sources.length === 0 && (
              <span className="text-xs text-muted-foreground">Add at least 1 source to continue</span>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
