/**
 * RFC 7807 problem+json → the message a human should actually read.
 *
 * Every backend error answers `application/problem+json` (see
 * `apps/api/errors.py`): `{type, title, status, detail, instance, extras}`.
 * `detail` is the per-occurrence reason ("A schedule named 'X' already exists
 * for this agent."); `title` is the stable, per-`type` class name. Throwing a
 * hardcoded "Failed to create schedule" discards both, so the UI tells the user
 * that something failed but never why — and the 409 the server went to the
 * trouble of explaining reads like a generic outage.
 *
 * `openapi-fetch` hands the PARSED error body back as its `error` value, but
 * types it off whatever error responses the schema happens to declare (often
 * `unknown`). So narrow at runtime rather than trusting the type — a non-JSON
 * error (a proxy's HTML 502) lands here too and must fall back cleanly.
 *
 * Kept pure + separate so it's unit-testable and so the other api/ modules —
 * which all still throw the generic string — can adopt it later without a
 * rewrite.
 */
export function problemMessage(error: unknown, fallback: string): string {
  if (error && typeof error === "object") {
    const body = error as { detail?: unknown; title?: unknown };
    if (typeof body.detail === "string" && body.detail.trim()) {
      return body.detail;
    }
    // `detail` is optional in the Problem model; `title` is not. A schedule
    // conflict carries both, but a bare validation error may only carry title.
    if (typeof body.title === "string" && body.title.trim()) {
      return body.title;
    }
  }
  return fallback;
}
