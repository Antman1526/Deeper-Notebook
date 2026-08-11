import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import React from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import apiClient from '@/lib/api/client'

import { useSystemStatus } from './use-system-status'

vi.mock('@/lib/api/client', () => ({
  default: {
    get: vi.fn(),
  },
}))

function wrapper({ children }: { children: React.ReactNode }) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return React.createElement(QueryClientProvider, { client }, children)
}

describe('useSystemStatus', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('maps a non-Readyz response into a safe not_ready shape', async () => {
    vi.mocked(apiClient.get).mockResolvedValue({
      data: { detail: 'Not Found' },
    } as never)

    const { result } = renderHook(() => useSystemStatus(), { wrapper })

    await waitFor(() => expect(result.current.isLoading).toBe(false))

    expect(result.current.data).toEqual({
      status: 'not_ready',
      checks: {
        database: 'unknown',
        database_error: 'Invalid readiness response',
        migrations_applied: false,
        migrations_pending: false,
        migrations_error: null,
      },
    })
  })
})
