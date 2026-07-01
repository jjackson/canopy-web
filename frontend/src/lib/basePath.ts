/**
 * Prefix a root-relative canopy-web path with the app's deployed base path.
 *
 * canopy-web can be served under a sub-path (e.g. `https://labs.connect.dimagi.com/canopy/`).
 * Vite builds the SPA with `base=/canopy/`, so assets and the router resolve
 * correctly — but content URLs like `/walkthrough/<id>/content` (built by
 * `walkthroughContentUrl`, or returned by the run-package API as
 * `content_url`) are ROOT-relative. As a `<video>`/`<iframe>` `src` those
 * resolve against the origin (`/walkthrough/<id>/content`), bypassing the `/canopy`
 * prefix, so the reverse proxy never routes them to canopy-web → 404 and the
 * video never loads.
 *
 * `withBase` makes such a path base-aware using `import.meta.env.BASE_URL`
 * (`"/canopy/"` in the deployed build, `"/"` in local dev). Absolute URLs and
 * already-based paths pass through unchanged.
 */
export function withBase(path: string): string;
export function withBase(path: null | undefined): null | undefined;
export function withBase(
  path: string | null | undefined,
): string | null | undefined {
  if (!path) return path;
  if (/^https?:\/\//.test(path)) return path; // absolute — leave it
  const base = import.meta.env.BASE_URL || "/"; // e.g. "/canopy/" or "/"
  // Idempotent: don't double-prefix a path that already carries the base.
  if (base !== "/" && (path === base || path.startsWith(base))) return path;
  return base + path.replace(/^\//, "");
}
