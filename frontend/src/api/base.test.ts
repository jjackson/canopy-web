import { describe, it, expect } from 'vitest'
import { joinBase, normalizeBase } from './base'

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
