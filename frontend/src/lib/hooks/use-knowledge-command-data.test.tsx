import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { searchApi } from '@/lib/api/search'
import { vaultApi } from '@/lib/api/vault'
import {
  useKnowledgeCatalog,
  useKnowledgeIndexedSearch,
} from './use-knowledge-command-data'

vi.mock('@/lib/api/vault', async importOriginal => {
  const actual = await importOriginal<typeof import('@/lib/api/vault')>()
  return { ...actual, vaultApi: { ...actual.vaultApi, files: vi.fn() } }
})
vi.mock('@/lib/api/search', () => ({
  searchApi: { search: vi.fn() },
}))

const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })}>
    {children}
  </QueryClientProvider>
)

describe('knowledge command data', () => {
  beforeEach(() => vi.resetAllMocks())
  afterEach(() => vi.useRealTimers())

  it('keeps healthy catalogs when one vault fails', async () => {
    vi.mocked(vaultApi.files)
      .mockResolvedValueOnce([{
        id: 'file:one',
        note_id: 'note:one',
        vault_id: 'vault:one',
        relative_path: 'One.md',
        file_kind: 'markdown',
        format: 'obsidian',
        content_hash: 'a'.repeat(64),
        parse_status: 'parsed',
        size_bytes: 1,
        modified_ns: 1,
        encoding: 'utf-8',
        newline: 'lf',
        deleted_state: 'present',
      }])
      .mockRejectedValueOnce(new Error('offline'))

    const { result } = renderHook(() => useKnowledgeCatalog([
      { id: 'vault:one', name: 'One', format_mode: 'obsidian',
        state: 'ready-read-only', watch_enabled: false },
      { id: 'vault:two', name: 'Two', format_mode: 'logseq',
        state: 'ready-read-only', watch_enabled: false },
    ], [], true), { wrapper })

    await waitFor(() => expect(result.current.isLoading).toBe(false))
    expect(result.current.candidates.map(item => item.noteId)).toEqual(['note:one'])
    expect(result.current.failedVaultCount).toBe(1)
  })

  it('debounces text search and never starts vector search automatically', async () => {
    vi.useFakeTimers()
    vi.mocked(searchApi.search).mockResolvedValue({
      results: [],
      total_count: 0,
      search_type: 'text',
    })
    const { rerender } = renderHook(
      ({ query }) => useKnowledgeIndexedSearch(query, true),
      { initialProps: { query: 're' }, wrapper },
    )
    rerender({ query: 'research' })

    expect(searchApi.search).not.toHaveBeenCalled()
    await act(async () => {
      await vi.advanceTimersByTimeAsync(249)
    })
    expect(searchApi.search).not.toHaveBeenCalled()
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1)
    })
    expect(searchApi.search).toHaveBeenCalledTimes(1)
    expect(searchApi.search).toHaveBeenCalledWith(expect.objectContaining({
      query: 'research',
      type: 'text',
    }))
    expect(searchApi.search).not.toHaveBeenCalledWith(expect.objectContaining({
      type: 'vector',
    }))
  })

  it('suppresses resolved text data while a newer query is debouncing', async () => {
    vi.useFakeTimers()
    let resolveFirst: (value: { results: []; total_count: number; search_type: string }) => void
    let resolveSecond: (value: { results: []; total_count: number; search_type: string }) => void
    const first = new Promise<{ results: []; total_count: number; search_type: string }>(resolve => {
      resolveFirst = resolve
    })
    const second = new Promise<{ results: []; total_count: number; search_type: string }>(resolve => {
      resolveSecond = resolve
    })
    vi.mocked(searchApi.search)
      .mockReturnValueOnce(first)
      .mockReturnValueOnce(second)

    const { result, rerender } = renderHook(
      ({ query }) => useKnowledgeIndexedSearch(query, true),
      { initialProps: { query: 'alpha' }, wrapper },
    )
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
    })
    await act(async () => {
      await vi.advanceTimersByTimeAsync(250)
    })
    expect(searchApi.search).toHaveBeenCalledTimes(1)
    await act(async () => {
      resolveFirst!({ results: [], total_count: 0, search_type: 'text' })
      await vi.advanceTimersByTimeAsync(0)
    })
    expect(result.current.text.data?.search_type).toBe('text')

    rerender({ query: 'beta' })
    expect(result.current.text.isCurrent).toBe(false)
    expect(result.current.text.data).toBeUndefined()
    await act(async () => {
      await vi.advanceTimersByTimeAsync(249)
    })
    expect(result.current.text.data).toBeUndefined()
    expect(searchApi.search).toHaveBeenCalledTimes(1)
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1)
    })
    expect(result.current.text.data).toBeUndefined()
    await act(async () => {
      resolveSecond!({ results: [], total_count: 0, search_type: 'text' })
      await vi.advanceTimersByTimeAsync(0)
    })
    expect(result.current.text.isCurrent).toBe(true)
    expect(result.current.text.data?.search_type).toBe('text')
  })

  it('starts vector search only through the explicit semantic action', async () => {
    vi.mocked(searchApi.search).mockResolvedValue({
      results: [],
      total_count: 0,
      search_type: 'vector',
    })
    const { result } = renderHook(
      () => useKnowledgeIndexedSearch('research', false),
      { wrapper },
    )

    act(() => result.current.runSemanticSearch())

    await waitFor(() => expect(result.current.semantic.isSuccess).toBe(true))
    expect(searchApi.search).toHaveBeenCalledTimes(1)
    expect(searchApi.search).toHaveBeenCalledWith(expect.objectContaining({
      query: 'research',
      type: 'vector',
    }))
  })
})
