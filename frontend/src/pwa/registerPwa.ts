import { registerSW } from 'virtual:pwa-register'

// Always auto-update.
//
// `registerType: 'autoUpdate'` (vite.config.ts) makes the app adopt a new service
// worker + reload — but ONLY checks for one on page load. A long-lived open client
// (the installed PWA, the menubar WKWebView, a tab left open for days) therefore
// never notices a new deploy and serves a stale bundle forever. That is exactly how
// the Sessions surface got stuck on a pre-feature bundle.
//
// So we poll: check for a new SW on an interval AND whenever the app regains focus
// (menubar reopened, tab refocused). When update() finds one, autoUpdate skips
// waiting and reloads on its own — no prompt, no manual hard-refresh.
const UPDATE_INTERVAL_MS = 60_000

export function registerPwa(): void {
  if (typeof window === 'undefined' || !('serviceWorker' in navigator)) return

  registerSW({
    immediate: true,
    onRegisteredSW(swUrl, registration) {
      if (!registration) return

      const check = async (): Promise<void> => {
        // Skip while an install is mid-flight or we're offline — retry next tick.
        if (registration.installing || !navigator.onLine) return
        try {
          // Bypass the HTTP cache so we actually see a freshly deployed sw.js;
          // a 200 means the server is reachable, so it's worth asking the browser
          // to re-evaluate the registration.
          const resp = await fetch(swUrl, {
            cache: 'no-store',
            headers: { 'cache-control': 'no-cache' },
          })
          if (resp.status === 200) await registration.update()
        } catch {
          // Offline / transient network error — the next tick will retry.
        }
      }

      setInterval(() => void check(), UPDATE_INTERVAL_MS)
      window.addEventListener('focus', () => void check())
      document.addEventListener('visibilitychange', () => {
        if (document.visibilityState === 'visible') void check()
      })
    },
  })
}
