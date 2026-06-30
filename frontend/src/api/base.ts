/**
 * Deployment base-path helpers.
 *
 * canopy-web runs either at the root ("/" — GCP / local) or under a path prefix
 * ("/canopy/" as a labs tenant on labs.connect.dimagi.com). Vite bakes the
 * prefix into `import.meta.env.BASE_URL`.
 *
 * The generated openapi-fetch client (`apiV2`) already carries this prefix via
 * its `baseUrl`. Hand-rolled raw-`fetch` clients do NOT — a literal
 * `fetch('/api/...')` resolves against the document origin, so under /canopy it
 * hits the ROOT tenant (connect-labs) and 404s. Those clients must wrap their
 * backend paths in `apiUrl()`.
 */

/** Strip a single trailing slash so a base concatenates cleanly with a path. */
export function normalizeBase(base: string): string {
  return base.replace(/\/$/, '')
}

/**
 * Prefix a root-relative backend path with a deployment base. At the root
 * deployment the base is "/" (→ "") and the path is unchanged; under /canopy
 * it becomes "/canopy/api/...". Kept pure (base passed in) so it's unit-testable
 * without stubbing `import.meta.env`.
 */
export function joinBase(base: string, path: string): string {
  return `${normalizeBase(base)}${path}`
}

/** The live deployment prefix ("" at root, "/canopy" as a labs tenant). */
export const API_BASE = normalizeBase(import.meta.env.BASE_URL)

/** Prefix a backend path (e.g. "/api/system/overview") with the live base. */
export function apiUrl(path: string): string {
  return joinBase(import.meta.env.BASE_URL, path)
}
