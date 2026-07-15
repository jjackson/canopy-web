import { describe, it, expect } from 'vitest'
import { urlBase64ToUint8Array } from './usePush'

describe('urlBase64ToUint8Array', () => {
  // PushManager.subscribe() takes applicationServerKey as raw BYTES. The VAPID
  // public key arrives as urlsafe-base64. Get this wrong and subscribe() throws
  // an opaque InvalidCharacterError with no hint about the cause.
  it('decodes urlsafe base64 to the raw key bytes', () => {
    // "hello" in urlsafe base64, unpadded
    const out = urlBase64ToUint8Array('aGVsbG8')
    expect(Array.from(out)).toEqual([104, 101, 108, 108, 111])
  })

  it('handles the - and _ substitutions urlsafe base64 uses', () => {
    // 0xfb 0xff decodes from "+/8=" in standard base64 → "-_8" urlsafe
    const out = urlBase64ToUint8Array('-_8')
    expect(Array.from(out)).toEqual([251, 255])
  })

  it('pads correctly — a real VAPID key is 65 raw bytes', () => {
    const key = 'BEl6-2xUX7c'.padEnd(87, 'A') // 87 chars ≈ 65 bytes unpadded
    expect(urlBase64ToUint8Array(key).length).toBe(65)
  })
})
