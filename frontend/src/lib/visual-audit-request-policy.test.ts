import { describe, expect, it } from 'vitest'

import {
  isAllowedLoopbackHostname,
  isExternalRequest,
} from './visual-audit-request-policy'

describe('visual audit outbound-request policy', () => {
  it('allows only exact loopback authorities, including bracketed IPv6', () => {
    expect(isExternalRequest('http://localhost:3117/api/health')).toBe(false)
    expect(isExternalRequest('http://127.0.0.1:3117/api/health')).toBe(false)
    expect(isExternalRequest('http://[::1]:3117/api/health')).toBe(false)
  })

  it('rejects hostile loopback-looking hostnames without making a request', () => {
    expect(isAllowedLoopbackHostname('attacker127.0.0.1')).toBe(false)
    expect(isAllowedLoopbackHostname('notlocalhost')).toBe(false)
    expect(isExternalRequest('http://attacker127.0.0.1.example/api/health')).toBe(true)
    expect(isExternalRequest('http://notlocalhost/api/health')).toBe(true)
  })
})
