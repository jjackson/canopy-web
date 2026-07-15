import { useEffect, useState } from 'react'
import type { Schedule } from '@/api/schedules'
import { createSchedule, deleteSchedule, previewCron, updateSchedule } from '@/api/schedules'

const PRESETS: { label: string; cron: string }[] = [
  { label: 'Weekly — Friday 9am', cron: '0 9 * * 5' },
  { label: 'Weekly — Monday 9am', cron: '0 9 * * 1' },
  { label: 'Monthly — 1st, 9am', cron: '0 9 1 * *' },
  { label: 'Daily — 9am', cron: '0 9 * * *' },
]

/**
 * Declare (or amend) one recurring activity. The point of the whole surface is
 * the "Next runs" panel: it answers "does this cron mean what I think it
 * means?" at edit time, from the SERVER's own next_slots() — instead of next
 * Friday, when it silently doesn't fire.
 */
export function ScheduleEditor({
  agentSlug,
  schedule,
  onClose,
  onSaved,
}: {
  agentSlug: string
  schedule: Schedule | null
  onClose: () => void
  onSaved: () => void
}) {
  const [name, setName] = useState(schedule?.name ?? '')
  const [prompt, setPrompt] = useState(schedule?.prompt ?? '')
  const [cron, setCron] = useState(schedule?.cron ?? '0 9 * * 5')
  const [tz, setTz] = useState(schedule?.timezone ?? Intl.DateTimeFormat().resolvedOptions().timeZone)
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)
  const [preview, setPreview] = useState<string[]>([])
  const [previewError, setPreviewError] = useState('')

  // Ask the SERVER when this cron would actually run — debounced, because the
  // user is mid-type. Never re-implement cron here: a client parser that says
  // "Fridays" while the server fires Thursdays is the exact failure the preview
  // exists to catch.
  useEffect(() => {
    let cancelled = false
    const timer = setTimeout(() => {
      previewCron(agentSlug, cron, tz)
        .then((runs) => {
          if (cancelled) return
          setPreview(runs)
          setPreviewError('')
        })
        .catch(() => {
          if (cancelled) return
          setPreview([])
          setPreviewError('Not a valid schedule.')
        })
    }, 300)
    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [agentSlug, cron, tz])

  async function onSave() {
    setSaving(true)
    setError('')
    try {
      if (schedule) {
        await updateSchedule(agentSlug, schedule.id, { name, prompt, cron, timezone: tz })
      } else {
        await createSchedule(agentSlug, {
          name,
          prompt,
          cron,
          timezone: tz,
          // The server's own defaults, restated because the generated ScheduleIn
          // marks every defaulted field required. Routing/grace/notify are not
          // exposed here yet — a schedule you can't reason about is worse than
          // one with fewer knobs.
          enabled: true,
          routing: 'prefer_local',
          grace_minutes: 120,
          notify: ['inbox'],
        })
      }
      onSaved()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save the schedule.')
    } finally {
      setSaving(false)
    }
  }

  async function onDelete() {
    if (!schedule) return
    setSaving(true)
    try {
      await deleteSchedule(agentSlug, schedule.id)
      onSaved()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not delete the schedule.')
      setSaving(false)
    }
  }

  return (
    // Scrim tokenized as bg-background/… (the AppLayout mobile-nav precedent) so
    // it dims correctly in BOTH themes — a fixed black scrim only reads right in
    // the light one.
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-background/70 p-4">
      <div className="w-full max-w-lg rounded-lg border border-border bg-card p-4">
        <h3 className="mb-3 text-sm font-medium text-foreground">
          {schedule ? 'Edit schedule' : 'New schedule'}
        </h3>

        <label className="mb-1 block text-[11px] text-muted-foreground">Name</label>
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Weekly manager report"
          className="mb-3 w-full rounded border border-input bg-input px-2 py-1 text-[13px] text-foreground"
        />

        <label className="mb-1 block text-[11px] text-muted-foreground">Prompt</label>
        <input
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          placeholder="/echo:manager-report"
          className="mb-3 w-full rounded border border-input bg-input px-2 py-1 font-mono text-[13px] text-foreground"
        />

        <label className="mb-1 block text-[11px] text-muted-foreground">When</label>
        <div className="mb-2 flex flex-wrap gap-1">
          {PRESETS.map((p) => (
            <button
              key={p.cron}
              type="button"
              onClick={() => setCron(p.cron)}
              className={`rounded border px-2 py-0.5 text-[11px] ${
                cron === p.cron
                  ? 'border-primary text-primary'
                  : 'border-input text-foreground-secondary hover:bg-muted'
              }`}
            >
              {p.label}
            </button>
          ))}
        </div>
        <div className="mb-3 flex gap-2">
          <input
            value={cron}
            onChange={(e) => setCron(e.target.value)}
            aria-label="Cron expression"
            className="w-40 rounded border border-input bg-input px-2 py-1 font-mono text-[13px] text-foreground"
          />
          <input
            value={tz}
            onChange={(e) => setTz(e.target.value)}
            aria-label="Timezone"
            className="flex-1 rounded border border-input bg-input px-2 py-1 text-[13px] text-foreground"
          />
        </div>

        <div className="mb-3 rounded border border-border bg-muted/40 px-2 py-1.5">
          <p className="mb-0.5 text-[11px] text-muted-foreground">Next runs</p>
          {previewError ? (
            <p className="text-[11px] text-destructive">{previewError}</p>
          ) : preview.length === 0 ? (
            <p className="text-[11px] text-foreground-subtle">—</p>
          ) : (
            <ul className="text-[11px] text-foreground-secondary">
              {preview.map((iso) => (
                <li key={iso}>
                  {new Date(iso).toLocaleString(undefined, {
                    weekday: 'short',
                    month: 'short',
                    day: 'numeric',
                    hour: '2-digit',
                    minute: '2-digit',
                  })}
                </li>
              ))}
            </ul>
          )}
        </div>

        {error && <p className="mb-3 text-[11px] text-destructive">{error}</p>}

        <div className="flex items-center justify-between">
          <div>
            {schedule && (
              <button
                type="button"
                onClick={() => void onDelete()}
                className="text-[11px] text-destructive hover:underline"
              >
                Delete
              </button>
            )}
          </div>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={onClose}
              className="rounded border border-input px-3 py-1 text-[11px] text-foreground-secondary hover:bg-muted"
            >
              Cancel
            </button>
            <button
              type="button"
              disabled={saving || !name.trim() || !prompt.trim()}
              onClick={() => void onSave()}
              className="rounded bg-primary px-3 py-1 text-[11px] text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
            >
              {saving ? 'Saving…' : 'Save'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
