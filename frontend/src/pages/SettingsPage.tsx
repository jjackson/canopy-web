import { useEffect, useState, useRef, useCallback } from 'react'
import { api } from '@/api/client'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'

type Step = 'idle' | 'loading' | 'awaiting_code' | 'submitting' | 'complete' | 'error'

export function SettingsPage() {
  const [aiStatus, setAiStatus] = useState<{
    backend: string; ready: boolean; detail: string
  } | null>(null)
  const [step, setStep] = useState<Step>('idle')
  const [authUrl, setAuthUrl] = useState<string | null>(null)
  const [code, setCode] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [tokenPreview, setTokenPreview] = useState<string | null>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const refreshStatus = useCallback(() => {
    api.getAiStatus().then(setAiStatus).catch(() => {})
  }, [])

  useEffect(() => {
    refreshStatus()
  }, [refreshStatus])

  // Poll for auth completion while awaiting code (browser might complete it)
  useEffect(() => {
    if (step !== 'awaiting_code') return
    pollRef.current = setInterval(async () => {
      try {
        const result = await api.authPoll()
        if (result.authenticated) {
          setStep('complete')
          refreshStatus()
        }
      } catch { /* ignore */ }
    }, 2000)
    return () => { if (pollRef.current) clearInterval(pollRef.current) }
  }, [step, refreshStatus])

  async function handleStartLogin() {
    setStep('loading')
    setError(null)
    setAuthUrl(null)
    setCode('')
    setTokenPreview(null)
    try {
      const result = await api.authStart()
      if (result.status === 'complete') {
        setStep('complete')
        refreshStatus()
      } else {
        setAuthUrl(result.auth_url)
        setStep('awaiting_code')
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start login')
      setStep('error')
    }
  }

  async function handleSubmitCode() {
    if (!code.trim()) return
    setStep('submitting')
    setError(null)
    try {
      const result = await api.authComplete(code.trim())
      setTokenPreview(result.token_preview)
      setStep('complete')
      refreshStatus()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to complete login')
      setStep('awaiting_code')
    }
  }

  return (
    <div className="space-y-5 max-w-xl">
      <div>
        <h1 className="text-lg font-semibold text-stone-100">Settings</h1>
        <p className="mt-0.5 text-xs text-stone-500">
          Manage your AI backend and authentication.
        </p>
      </div>

      {/* Current status */}
      <div className="rounded-xl border border-stone-800 bg-stone-900 p-5 space-y-3">
        <h2 className="text-[10px] uppercase tracking-wider font-semibold text-stone-500">AI Backend</h2>
        {aiStatus ? (
          <div className="flex items-center gap-3">
            <span className={
              aiStatus.ready
                ? 'inline-flex items-center gap-1.5 text-xs font-medium text-emerald-400 bg-emerald-400/10 border border-emerald-400/30 px-2 py-1 rounded'
                : 'inline-flex items-center gap-1.5 text-xs font-medium text-amber-400 bg-amber-400/10 border border-amber-400/30 px-2 py-1 rounded'
            }>
              <span className={`w-1.5 h-1.5 rounded-full ${aiStatus.ready ? 'bg-emerald-400 shadow-[0_0_6px_rgba(74,222,128,0.5)]' : 'bg-amber-400 shadow-[0_0_6px_rgba(251,191,36,0.5)]'}`} />
              {aiStatus.ready ? 'Connected' : 'Not connected'}
            </span>
            <span className="text-sm text-stone-400">{aiStatus.detail}</span>
          </div>
        ) : (
          <span className="text-sm text-stone-600">Loading...</span>
        )}
      </div>

      {/* Login flow */}
      {aiStatus && !aiStatus.ready && (
        <div className="rounded-xl border border-stone-800 bg-stone-900 p-5 space-y-4">
          <div>
            <h2 className="text-sm font-semibold text-stone-100">Connect Claude Subscription</h2>
            <p className="mt-1 text-sm text-stone-500">
              Sign in with your Anthropic account to use your Claude subscription for AI calls.
            </p>
          </div>

          {step === 'idle' || step === 'error' || step === 'loading' ? (
            <div className="space-y-3">
              <Button size="sm" onClick={handleStartLogin} disabled={step === 'loading'}>
                {step === 'loading' ? (
                  <span className="flex items-center gap-2">
                    <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                    </svg>
                    Starting login...
                  </span>
                ) : 'Start Login'}
              </Button>
              {step === 'loading' && (
                <p className="text-xs text-stone-500">Generating authorization link (a few seconds)...</p>
              )}
              {error && (
                <p className="text-sm text-red-400">{error}</p>
              )}
            </div>
          ) : step === 'awaiting_code' ? (
            <div className="space-y-4">
              <div className="space-y-2">
                <p className="text-sm text-stone-300">
                  <span className="text-orange-400 font-semibold">1.</span> Click the link below to authorize:
                </p>
                <a
                  href={authUrl!}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="block text-sm text-orange-400 hover:text-orange-300 underline underline-offset-2 break-all"
                >
                  Open Anthropic Login ↗
                </a>
              </div>
              <div className="space-y-2">
                <p className="text-sm text-stone-300">
                  <span className="text-orange-400 font-semibold">2.</span> After authorizing, paste the code shown on the callback page:
                </p>
                <div className="flex gap-2">
                  <Input
                    placeholder="Paste authorization code..."
                    value={code}
                    onChange={(e) => setCode(e.target.value)}
                    onKeyDown={(e) => { if (e.key === 'Enter') handleSubmitCode() }}
                    className="font-mono text-sm"
                  />
                  <Button size="sm" onClick={handleSubmitCode} disabled={!code.trim()}>
                    Submit
                  </Button>
                </div>
              </div>
              {error && (
                <p className="text-sm text-red-400">{error}</p>
              )}
            </div>
          ) : step === 'submitting' ? (
            <p className="text-sm text-stone-400">Completing authentication...</p>
          ) : null}
        </div>
      )}

      {/* Success state */}
      {(step === 'complete' || aiStatus?.ready) && (
        <div className="rounded-xl border border-emerald-400/30 bg-emerald-400/10 p-4 space-y-1">
          <p className="text-sm font-semibold text-emerald-400">Authenticated</p>
          {tokenPreview && (
            <p className="text-xs text-emerald-400/80 font-mono">{tokenPreview}</p>
          )}
          <p className="text-xs text-emerald-400/70">
            Claude CLI is connected via your subscription. Token persists across container restarts.
          </p>
        </div>
      )}
    </div>
  )
}
