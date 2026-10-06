import { describe, expect, it } from 'vitest'

import { benchmarkActionError } from './benchmark-errors'

// v0.8.130 — "This desktop runtime cannot cancel…" is true only when the runtime has no
// such endpoint (the bundled API has none: 404 for cancel, 405 for reset). A server
// error or a lost connection said the same thing, which sent people looking for a
// missing feature instead of a failed request.

const t = (key: string) => `t:${key}`
const httpError = (status: number, detail?: string) => ({
  isAxiosError: true,
  response: { status, data: detail ? { detail } : {} },
  message: `Request failed with status code ${status}`,
})

describe('benchmarkActionError', () => {
  it('says the runtime cannot do it only when the endpoint is missing', () => {
    for (const status of [404, 405, 501]) {
      expect(benchmarkActionError('cancel', httpError(status), t), String(status)).toEqual({
        title: 'This desktop runtime cannot cancel the running benchmark.',
      })
      expect(benchmarkActionError('reset', httpError(status), t), String(status)).toEqual({
        title: 'This desktop runtime cannot reset benchmark history.',
      })
    }
  })

  it('reports any other failure as a failed request, with a readable reason', () => {
    const cancel = benchmarkActionError('cancel', httpError(500, 'Benchmark worker crashed'), t)
    expect(cancel.title).toBe('Could not cancel the running benchmark.')
    expect(cancel.description).toBeTruthy()
    expect(cancel.description).not.toMatch(/status code/)

    const reset = benchmarkActionError('reset', new Error('Network Error'), t)
    expect(reset.title).toBe('Could not reset benchmark history.')
    expect(reset.description).toBeTruthy()
  })
})
