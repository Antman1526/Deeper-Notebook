// v0.8.130 — one toast per failure. A failed save used to show two error toasts: the
// interceptor's generic "Server error…" and the caller's own message (76 mutations
// and ~15 direct calls report their own failures). The generic toast is now a
// fallback: it waits one task, and a caller that reports the error first claims it.

import { act, renderHook } from '@testing-library/react'
import { QueryClientProvider, useMutation } from '@tanstack/react-query'
import { AxiosError, type InternalAxiosRequestConfig } from 'axios'
import React from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const toastError = vi.hoisted(() => vi.fn())
vi.mock('sonner', () => ({ toast: Object.assign(vi.fn(), { error: toastError, success: vi.fn() }) }))
vi.mock('@/lib/config', () => ({ getApiUrl: async () => 'http://api.test' }))

import { apiClient, isErrorReported, markErrorReported } from './client'
import { createQueryClient } from './query-client'
import { useAddSourcesToNotebook } from '@/lib/hooks/use-sources'

const GENERIC = 'Server error. Check the API log (~/.deeper-notebook/logs/api.log) for details.'
let requests = 0

function serverError(config: InternalAxiosRequestConfig): Promise<never> {
  requests += 1
  return Promise.reject(new AxiosError('Request failed with status code 500', 'ERR_BAD_RESPONSE', config, {}, {
    status: 500, statusText: 'Internal Server Error', data: { detail: 'boom' }, headers: {}, config,
  }))
}

// Every test uses its own URL: the generic toast is deduped per (status, URL) for 5s.
let route = 0
const nextUrl = () => `/error-toasts/${(route += 1)}`
const settle = () => act(() => new Promise((resolve) => setTimeout(resolve, 20)))

function Wrapper({ children }: { children: React.ReactNode }) {
  const client = React.useMemo(() => createQueryClient(), [])
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>
}

describe('5xx error toasts', () => {
  const originalAdapter = apiClient.defaults.adapter
  beforeEach(() => {
    toastError.mockClear()
    requests = 0
    apiClient.defaults.adapter = serverError
  })
  afterEach(() => {
    apiClient.defaults.adapter = originalAdapter
  })

  it('keeps the generic toast for a failure nobody reports', async () => {
    await apiClient.post(nextUrl()).catch(() => undefined)
    await settle()
    expect(toastError.mock.calls.map(([message]) => message)).toEqual([GENERIC])
  })

  it('lets a caller that reports the failure show the only toast', async () => {
    try {
      await apiClient.post(nextUrl())
    } catch (error) {
      markErrorReported(error)
      toastError('Could not save the note.')
    }
    await settle()
    expect(toastError.mock.calls.map(([message]) => message)).toEqual(['Could not save the note.'])
  })

  it('shows one toast, sends one request, for a mutation with its own onError', async () => {
    const url = nextUrl()
    const { result } = renderHook(() => useMutation({
      mutationFn: () => apiClient.delete(url),
      onError: () => toastError('The MCP server could not be removed.'),
    }), { wrapper: Wrapper })

    await act(async () => {
      result.current.mutate()
    })
    await settle()

    expect(toastError.mock.calls.map(([message]) => message)).toEqual(['The MCP server could not be removed.'])
    expect(requests).toBe(1)
  })

  it('keeps the generic toast for a mutation without onError', async () => {
    const url = nextUrl()
    const { result } = renderHook(() => useMutation({ mutationFn: () => apiClient.post(url) }), { wrapper: Wrapper })

    await act(async () => {
      result.current.mutate()
    })
    await settle()

    expect(toastError.mock.calls.map(([message]) => message)).toEqual([GENERIC])
  })

  it('lets a caller skip its own toast when the mutation already reported the failure', async () => {
    const url = nextUrl()
    const { result } = renderHook(() => useMutation({
      mutationFn: () => apiClient.post(url),
      onError: () => toastError('Could not create the note.'),
    }), { wrapper: Wrapper })

    await act(async () => {
      try {
        await result.current.mutateAsync()
      } catch (error) {
        if (!isErrorReported(error)) toastError('Could not save to notebooks.')
      }
    })
    await settle()

    expect(toastError.mock.calls.map(([message]) => message)).toEqual(['Could not create the note.'])
  })

  it('reports a partly failed batch once, not once per failed request', async () => {
    const { result } = renderHook(() => useAddSourcesToNotebook(), { wrapper: Wrapper })

    await act(async () => {
      await result.current.mutateAsync({ notebookId: `notebook:${route += 1}`, sourceIds: ['source:a', 'source:b'] })
    })
    await settle()

    // Only the hook's summary toast: no generic toast for each failed source.
    expect(toastError).toHaveBeenCalledTimes(1)
    expect(toastError.mock.calls[0][0]).not.toBe(GENERIC)
    expect(requests).toBe(2)
  })

  it('lets a mutation declare that its callers report errors (meta.reportsErrors)', async () => {
    const url = nextUrl()
    const { result } = renderHook(() => useMutation({
      mutationFn: () => apiClient.post(url),
      meta: { reportsErrors: true },
    }), { wrapper: Wrapper })

    await act(async () => {
      result.current.mutate(undefined, { onError: () => toastError('Could not cancel the download.') })
    })
    await settle()

    expect(toastError.mock.calls.map(([message]) => message)).toEqual(['Could not cancel the download.'])
  })
})
