// Build a ws(s):// URL under the SPA base path (honors the /canopy prefix).
// buildWsUrl is the pure core so it unit-tests without a DOM; wsUrl reads window.

export function buildWsUrl(base: string, protocol: string, host: string, path: string): string {
  const b = base.replace(/\/$/, '')
  const proto = protocol === 'https:' ? 'wss:' : 'ws:'
  const clean = path.replace(/^\//, '')
  return `${proto}//${host}${b}/${clean}`
}

export function wsUrl(path: string): string {
  return buildWsUrl(import.meta.env.BASE_URL, window.location.protocol, window.location.host, path)
}
