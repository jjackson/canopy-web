// When a new build ships a NEW top-level route, a browser still running the
// PREVIOUS bundle (served from the PWA service worker's precache until it
// updates) has no such route in its router. React Router then throws a
// "no match" for that path, which surfaces as the scary RouteErrorBoundary.
// The catch-all route (NotFound) recovers by reloading ONCE to pick up the
// freshened bundle — self-healing, exactly like `shouldBounceToLogin` in
// client.v2.ts recovers a lapsed session with a single bounce.
//
// The window makes the reload single-shot: if we reload and STILL land on the
// catch-all (the SW hadn't updated yet, or the URL is a genuine typo), we do
// NOT reload again — we show a real "page not found" instead of looping.
export const STALE_RELOAD_WINDOW_MS = 20_000;
const STALE_RELOAD_AT_KEY = "canopy:staleBundle:lastReloadAt";

/**
 * Pure decision, split out so it's unit-testable without a DOM (this codebase's
 * convention — see `shouldBounceToLogin`). Reload only if we have NOT already
 * reloaded within the window; a second landing inside it means the reload
 * didn't fix it, so stop and let the caller render a 404.
 */
export function shouldReloadForStaleBundle(lastReloadAt: number, now: number): boolean {
  return !(lastReloadAt > 0 && now - lastReloadAt < STALE_RELOAD_WINDOW_MS);
}

/**
 * Effectful wrapper: read the last-reload stamp, decide, and if we should,
 * stamp + reload. Returns true when it triggered a reload (so the caller can
 * render nothing while the navigation happens), false when it gave up and the
 * caller should render the not-found UI. sessionStorage (not a module var) so
 * the stamp survives the full-page reload; best-effort, since it can throw in
 * private mode.
 */
export function reloadOnceForStaleBundle(): boolean {
  let last = 0;
  try {
    last = Number(sessionStorage.getItem(STALE_RELOAD_AT_KEY)) || 0;
  } catch {
    /* sessionStorage unavailable — treat as "never reloaded" and allow the one reload */
  }
  if (!shouldReloadForStaleBundle(last, Date.now())) return false;
  try {
    sessionStorage.setItem(STALE_RELOAD_AT_KEY, String(Date.now()));
  } catch {
    /* unavailable — a best-effort guard is better than blocking the recovery */
  }
  window.location.reload();
  return true;
}
