import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '@/api/client'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'

type CollectionResult = { id: number }

export function NewCollectionPage() {
  const navigate = useNavigate()
  const [name, setName] = useState('')
  const [sourceText, setSourceText] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [step, setStep] = useState<string | null>(null)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()

    const trimmedName = name.trim()
    const trimmedSource = sourceText.trim()

    if (!trimmedName) {
      setError('Please enter a collection name.')
      return
    }
    if (!trimmedSource) {
      setError('Please paste source content.')
      return
    }

    setError(null)
    setSubmitting(true)

    try {
      // Step 1: Create collection
      setStep('Creating collection...')
      const collection = (await api.createCollection(trimmedName)) as CollectionResult

      // Step 2: Add source
      setStep('Adding source...')
      await api.addSource(collection.id, {
        source_type: 'text',
        title: trimmedName,
        content: trimmedSource,
      })

      // Step 3: Run analysis (synchronous - waits for AI to finish)
      setStep('Analyzing sources (this may take 30-60 seconds)...')
      const result = await api.analyzeWorkspace(collection.id)

      // Step 4: Navigate to workspace
      navigate(`/workspace/${result.session_id}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong.')
      setSubmitting(false)
      setStep(null)
    }
  }

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <div>
        <h1 className="text-lg font-semibold text-gray-900">New Skill from Source</h1>
        <p className="mt-1 text-sm text-gray-500">
          Paste a conversation, document, or transcript below. The AI will analyze it and
          propose a reusable skill with evaluation cases.
        </p>
      </div>

      {error && (
        <div className="rounded border border-red-200 bg-red-50 p-3 text-sm text-red-700">
          {error}
        </div>
      )}

      <form onSubmit={(e) => void handleSubmit(e)} className="space-y-4">
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
          <label htmlFor="source-content" className="mb-1 block text-sm font-medium text-gray-700">
            Source Content
          </label>
          <Textarea
            id="source-content"
            placeholder="Paste a conversation, transcript, or document here..."
            value={sourceText}
            onChange={(e) => setSourceText(e.target.value)}
            disabled={submitting}
            className="min-h-[300px]"
          />
        </div>

        <div className="flex items-center gap-3">
          <Button type="submit" disabled={submitting}>
            {submitting ? 'Working...' : 'Start Analysis'}
          </Button>
          {step && (
            <span className="text-sm text-gray-500">{step}</span>
          )}
        </div>
      </form>
    </div>
  )
}
