import { describe, expect, it } from 'vitest'

import { shouldRetryMutation } from './query-client'

describe('shouldRetryMutation', () => {
  it('does not retry client-side API errors', () => {
    expect(
      shouldRetryMutation(0, { response: { status: 413 } }),
    ).toBe(false)
    expect(
      shouldRetryMutation(0, { response: { status: 400 } }),
    ).toBe(false)
  })

  it('keeps one retry for transient or server-side failures', () => {
    expect(
      shouldRetryMutation(0, { response: { status: 502 } }),
    ).toBe(true)
    expect(shouldRetryMutation(0, new Error('Network Error'))).toBe(true)
    expect(
      shouldRetryMutation(1, { response: { status: 502 } }),
    ).toBe(false)
  })
})
