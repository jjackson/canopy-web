/**
 * CSRF bootstrap.
 *
 * Hits the bare Django view at /api/csrf/ to set the csrftoken cookie
 * before the first POST/PATCH/DELETE. NOT a Ninja v2 endpoint — this
 * is intentionally out-of-band because it sets a cookie via Django's
 * @ensure_csrf_cookie decorator, which doesn't fit the Ninja pattern.
 */
export async function bootstrapCsrf(): Promise<void> {
  await fetch('/api/csrf/', { credentials: 'same-origin' })
}
