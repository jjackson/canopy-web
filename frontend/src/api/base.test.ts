import { describe, it, expect } from 'vitest'
import { joinBase, normalizeBase, readCookieFrom } from './base'

describe('normalizeBase', () => {
  it('strips a single trailing slash', () => {
    expect(normalizeBase('/canopy/')).toBe('/canopy')
  })
  it('reduces the root base to an empty string', () => {
    expect(normalizeBase('/')).toBe('')
  })
})

describe('joinBase', () => {
  it('passes backend paths through unchanged at the root deployment', () => {
    expect(joinBase('/', '/api/system/overview')).toBe('/api/system/overview')
  })

  it('prefixes the tenant base under a path-prefixed deployment', () => {
    // The /canopy labs tenant: a raw "/api/..." would hit the root tenant and 404.
    expect(joinBase('/canopy/', '/api/system/overview')).toBe(
      '/canopy/api/system/overview',
    )
  })

  it('handles a base supplied without a trailing slash', () => {
    expect(joinBase('/canopy', '/api/x')).toBe('/canopy/api/x')
  })
})

describe('readCookieFrom', () => {
  it('extracts a named cookie value from the cookie string', () => {
    expect(
      readCookieFrom('a=1; csrftoken_canopy=abc123; b=2', 'csrftoken_canopy'),
    ).toBe('abc123')
  })

  it('reads a cookie at the start of the string', () => {
    expect(readCookieFrom('csrftoken=xyz; a=1', 'csrftoken')).toBe('xyz')
  })

  it('returns an empty string when the cookie is absent', () => {
    // The tenant cookie name matters: reading "csrftoken" when the server set
    // "csrftoken_canopy" is exactly the /canopy write-path bug this guards.
    expect(readCookieFrom('csrftoken_canopy=abc', 'csrftoken')).toBe('')
  })

  it('url-decodes the value', () => {
    expect(readCookieFrom('csrftoken=a%2Bb', 'csrftoken')).toBe('a+b')
  })
})
