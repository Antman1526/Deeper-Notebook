import { describe, expect, it } from 'vitest'

import { detectMac } from './use-is-mac'

describe('detectMac', () => {
  it('recognizes macOS from navigator.platform', () => {
    expect(detectMac({ platform: 'MacIntel' })).toBe(true)
  })

  it('treats Windows and Linux as non-Mac', () => {
    expect(detectMac({ platform: 'Win32' })).toBe(false)
    expect(detectMac({ platform: 'Linux x86_64' })).toBe(false)
  })

  it('prefers the UA client-hints platform when the browser provides it', () => {
    expect(detectMac({ platform: 'Win32', userAgentData: { platform: 'macOS' } })).toBe(true)
    expect(detectMac({ platform: 'MacIntel', userAgentData: { platform: 'Windows' } })).toBe(false)
  })

  it('falls back to non-Mac when the platform is unknown', () => {
    expect(detectMac({ platform: '' })).toBe(false)
  })
})
