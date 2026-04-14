import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { api, type MeResponse } from '@/api/client'

type AuthState =
  | { status: 'loading'; user: null }
  | { status: 'authenticated'; user: MeResponse }
  | { status: 'anonymous'; user: null }

const AuthContext = createContext<AuthState>({ status: 'loading', user: null })

export function useAuth(): AuthState {
  return useContext(AuthContext)
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({ status: 'loading', user: null })

  useEffect(() => {
    let cancelled = false
    async function boot() {
      try {
        await api.bootstrapCsrf()
        const me = await api.me()
        if (cancelled) return
        if (me) setState({ status: 'authenticated', user: me })
        else setState({ status: 'anonymous', user: null })
      } catch {
        if (!cancelled) setState({ status: 'anonymous', user: null })
      }
    }
    void boot()
    return () => {
      cancelled = true
    }
  }, [])

  if (state.status === 'loading') {
    return (
      <div className="min-h-screen bg-stone-950 text-stone-500 flex items-center justify-center text-sm">
        Loading…
      </div>
    )
  }

  if (state.status === 'anonymous') {
    return <LoginPrompt />
  }

  return <AuthContext.Provider value={state}>{children}</AuthContext.Provider>
}

function LoginPrompt() {
  const next = encodeURIComponent(window.location.pathname + window.location.search)
  const loginHref = `/accounts/google/login/?next=${next}`
  return (
    <div className="min-h-screen bg-stone-950 text-stone-200 flex items-center justify-center px-6">
      <div className="max-w-md w-full bg-stone-900 border border-stone-800 rounded-xl p-8 text-center">
        <h1 className="text-2xl font-semibold text-stone-100 mb-2">
          Canopy<span className="text-orange-400">.</span>
        </h1>
        <p className="text-sm text-stone-400 mb-6">
          Sign in with your Dimagi Google account to continue.
        </p>
        <a
          href={loginHref}
          className="inline-block w-full rounded-lg bg-orange-500 text-white font-medium py-2.5 hover:bg-orange-400 transition-colors"
        >
          Sign in with Google
        </a>
      </div>
    </div>
  )
}
