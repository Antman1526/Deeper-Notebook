import { getApiErrorMessage } from '@/lib/utils/error-handler'

// v0.8.130 — "This desktop runtime cannot …" only when the runtime has no such
// endpoint (the bundled API has no cancel or reset: 404 and 405). Anything else is a
// request that failed, and says why.

const UNSUPPORTED = new Set([404, 405, 501])

const COPY = {
  cancel: {
    unsupported: 'This desktop runtime cannot cancel the running benchmark.',
    failed: 'Could not cancel the running benchmark.',
  },
  reset: {
    unsupported: 'This desktop runtime cannot reset benchmark history.',
    failed: 'Could not reset benchmark history.',
  },
} as const

export function benchmarkActionError(
  action: keyof typeof COPY,
  error: unknown,
  t: (key: string) => string,
): { title: string; description?: string } {
  const status = (error as { response?: { status?: number } } | null)?.response?.status
  if (status !== undefined && UNSUPPORTED.has(status)) return { title: COPY[action].unsupported }
  return { title: COPY[action].failed, description: getApiErrorMessage(error, t) }
}
