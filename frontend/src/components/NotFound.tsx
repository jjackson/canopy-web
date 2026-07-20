import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { reloadOnceForStaleBundle } from "./staleBundle";

/**
 * Catch-all (`path: '*'`) route. An unmatched path usually means one of two
 * things: a genuine bad URL, or — right after a deploy that added a new
 * route — a browser still running the PREVIOUS bundle out of the PWA service
 * worker's precache, whose router doesn't know the new route yet.
 *
 * We treat it as the latter FIRST: reload once (the SW autoUpdates, so the
 * reload lands on the freshened bundle that DOES have the route). If we reload
 * and still end up here, `reloadOnceForStaleBundle` refuses to loop and we
 * render an honest "page not found" instead. This turns "Something broke" into
 * silent self-healing for the common post-deploy case.
 */
export function NotFound() {
  // Start as null: if we're going to reload, never flash the 404 first.
  const [reloading] = useState(() => reloadOnceForStaleBundle());
  useEffect(() => {
    /* the reload (if any) was already kicked off synchronously above */
  }, []);

  if (reloading) return null;

  return (
    <div className="max-w-2xl px-6 py-8">
      <div className="rounded-lg border border-border bg-card p-5">
        <span className="inline-flex rounded border border-border bg-muted px-1.5 py-0.5 text-[11px] text-muted-foreground">
          Page not found
        </span>
        <h2 className="mt-3 text-sm font-medium text-foreground">There’s nothing at this address.</h2>
        <p className="mt-1 text-[13px] text-foreground-secondary">
          The link may be out of date. If you just updated Canopy, a reload will pick up the latest
          version.
        </p>
        <p className="mt-2 text-[11px] text-foreground-subtle">
          <span className="font-mono break-all">{window.location.pathname}</span>
        </p>
        <div className="mt-4 flex gap-2">
          <button
            type="button"
            onClick={() => window.location.reload()}
            className="rounded bg-primary px-3 py-1 text-[11px] font-medium text-primary-foreground hover:bg-primary/90"
          >
            Reload
          </button>
          <Link
            to="/"
            className="rounded border border-input px-3 py-1 text-[11px] text-foreground-secondary hover:bg-muted"
          >
            Back to Canopy
          </Link>
        </div>
      </div>
    </div>
  );
}
