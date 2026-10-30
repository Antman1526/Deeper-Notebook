import { describe, expect, it } from 'vitest'

import { shouldRetryIdempotentMutation, shouldRetryMutation } from './query-client'

describe('shouldRetryMutation', () => {
  it('does not retry client-side API errors', () => {
    expect(
      shouldRetryMutation(0, { response: { status: 413 } }),
    ).toBe(false)
    expect(
      shouldRetryMutation(0, { response: { status: 400 } }),
    ).toBe(false)
  })

  // v0.8.130 — a retry repeats a write the server may already have applied, and
  // delays the caller's error report past the interceptor's fallback toast. Retry
  // only when no response arrived and the method is safe to repeat.
  it('does not retry once the server has answered, 5xx included', () => {
    for (const status of [500, 502, 503, 504]) {
      expect(shouldRetryMutation(0, { response: { status }, config: { method: 'delete' } }), String(status)).toBe(false)
    }
  })

  it('retries a lost request once when the method is safe to repeat', () => {
    for (const method of ['get', 'put', 'delete', 'head', 'options']) {
      expect(shouldRetryMutation(0, { config: { method } }), method).toBe(true)
      expect(shouldRetryMutation(1, { config: { method } }), method).toBe(false)
    }
  })

  it('never retries a lost POST or PATCH, which may already have been applied', () => {
    expect(shouldRetryMutation(0, { config: { method: 'post' } })).toBe(false)
    expect(shouldRetryMutation(0, { config: { method: 'patch' } })).toBe(false)
  })

  it('does not retry an error it cannot classify (no request config)', () => {
    expect(shouldRetryMutation(0, new Error('Network Error'))).toBe(false)
  })
})

// v0.8.130 — a mutation that sends an idempotency key (a stable request id, like the
// source-visual refresh) may repeat a lost request whatever its method.
describe('shouldRetryIdempotentMutation', () => {
  it('retries a lost request once, POST included', () => {
    expect(shouldRetryIdempotentMutation(0, { config: { method: 'post' } })).toBe(true)
    expect(shouldRetryIdempotentMutation(0, new Error('transient'))).toBe(true)
    expect(shouldRetryIdempotentMutation(1, new Error('transient'))).toBe(false)
  })

  it('does not retry once the server has answered', () => {
    expect(shouldRetryIdempotentMutation(0, { response: { status: 409 } })).toBe(false)
    expect(shouldRetryIdempotentMutation(0, { response: { status: 503 } })).toBe(false)
  })
})
