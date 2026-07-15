import { isRouteErrorResponse, Link, useRouteError } from 'react-router-dom'

/**
 * The app's error boundary, rendered as a route `errorElement`.
 *
 * `createBrowserRouter` is a DATA router, and its `errorElement` catches throws
 * from a route's own RENDER as well as from its loaders/actions — React Router
 * wires a real class boundary (`componentDidCatch`) around each route element
 * internally, so no hand-rolled class component is needed here. `<Suspense>`
 * does NOT do this: it only covers a lazy chunk's pending state, which is why a
 * render throw in one rail section used to white-screen the entire app.
 *
 * Granularity is the whole point (see `guarded()` in router.tsx): the boundary
 * hangs off EVERY route, so React Router swaps in the nearest one and the throw
 * is contained to the smallest replaceable surface. A section throw leaves the
 * agent workspace shell — and every other section's rail link — alive; a page
 * throw leaves the app header and nav alive. A single root boundary would catch
 * the same throws but blank the entire app, which is the failure we're fixing.
 */
export function RouteErrorBoundary() {
  const error = useRouteError()

  // A thrown Response (React Router's 404/redirect path) reads as a status, not
  // a message; everything else is an Error, or — rarely — a bare throw value.
  const message = isRouteErrorResponse(error)
    ? `${error.status} ${error.statusText}`
    : error instanceof Error
      ? error.message
      : typeof error === 'string'
        ? error
        : 'An unexpected error occurred.'

  // Never the primary UI: a stack is for whoever fixes it, not whoever hit it.
  const stack = error instanceof Error ? error.stack : undefined

  return (
    <div className="max-w-2xl px-6 py-8">
      <div className="rounded-lg border border-border bg-card p-5">
        <span className="inline-flex rounded border border-destructive/30 bg-destructive/10 px-1.5 py-0.5 text-[11px] text-destructive">
          Something broke
        </span>

        <h2 className="mt-3 text-sm font-medium text-foreground">This section didn’t load.</h2>
        <p className="mt-1 text-[13px] text-foreground-secondary">
          The rest of Canopy still works — use the navigation to go somewhere else, or try this
          section again.
        </p>

        {/* The honest bit. One line, muted, mono — enough to report with, calm
            enough not to look like the app caught fire. */}
        <p className="mt-3 break-words rounded border border-border bg-muted/40 px-2 py-1.5 font-mono text-[11px] text-muted-foreground">
          {message}
        </p>
        <p className="mt-2 text-[11px] text-foreground-subtle">
          If it keeps happening, report the message above along with this address:{' '}
          <span className="font-mono break-all">{window.location.pathname}</span>
        </p>

        <div className="mt-4 flex gap-2">
          {/* A full reload, not a re-render: the boundary can't know whether the
              throwing state lives in this component or came back from the
              server, so the only honest retry is "fetch it all again". */}
          <button
            type="button"
            onClick={() => window.location.reload()}
            className="rounded bg-primary px-3 py-1 text-[11px] font-medium text-primary-foreground hover:bg-primary/90"
          >
            Try again
          </button>
          {/* The escape hatch that works even when a reload re-crashes, because
              the throwing state is persisted server-side. */}
          <Link
            to="/"
            className="rounded border border-input px-3 py-1 text-[11px] text-foreground-secondary hover:bg-muted"
          >
            Back to Canopy
          </Link>
        </div>

        {import.meta.env.DEV && stack && (
          <details className="mt-4">
            <summary className="cursor-pointer text-[11px] text-muted-foreground">
              Stack trace (dev only)
            </summary>
            <pre className="mt-2 overflow-x-auto rounded border border-border bg-muted/40 p-2 text-[10px] text-foreground-subtle">
              {stack}
            </pre>
          </details>
        )}
      </div>
    </div>
  )
}
