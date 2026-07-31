import type { ReactNode } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/lib/api/knowledge-navigation', async (importOriginal) => {
  const original = await importOriginal<typeof import('@/lib/api/knowledge-navigation')>()
  return {
    ...original,
    knowledgeNavigationApi: {
      listBookmarks: vi.fn(), createBookmark: vi.fn(), updateBookmark: vi.fn(),
      deleteBookmark: vi.fn(), listFolders: vi.fn(), createFolder: vi.fn(),
      updateFolder: vi.fn(), deleteFolder: vi.fn(), listWorkspaces: vi.fn(),
      createWorkspace: vi.fn(), getWorkspace: vi.fn(), updateWorkspace: vi.fn(),
      duplicateWorkspace: vi.fn(), deleteWorkspace: vi.fn(), restorePlan: vi.fn(),
      randomNote: vi.fn(),
    },
  }
})

import { knowledgeNavigationApi } from '@/lib/api/knowledge-navigation'
import {
  knowledgeNavigationKeys,
  useCreateKnowledgeBookmark,
  useCreateKnowledgeFolder,
  useDeleteKnowledgeWorkspace,
  useRandomKnowledgeNote,
  useRestoreKnowledgeWorkspace,
} from './use-knowledge-navigation'

function wrapperFor(client: QueryClient) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>
  }
}

function queryClient(options: { retry?: number } = {}) {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: options.retry ?? false },
    },
  })
}

describe('knowledge navigation hooks', () => {
  beforeEach(() => vi.resetAllMocks())

  it('uses stable, collection-scoped keys rooted at knowledge-navigation', () => {
    expect(knowledgeNavigationKeys.root).toEqual(['knowledge-navigation'])
    expect(knowledgeNavigationKeys.bookmarks({ tags: ['Evidence'] })).toEqual([
      'knowledge-navigation', 'bookmarks', { tags: ['Evidence'] },
    ])
    expect(knowledgeNavigationKeys.folders).toEqual(['knowledge-navigation', 'folders'])
    expect(knowledgeNavigationKeys.workspaces).toEqual(['knowledge-navigation', 'workspaces'])
    expect(knowledgeNavigationKeys.workspace('named_knowledge_workspace:desk')).toEqual([
      'knowledge-navigation', 'workspaces', 'named_knowledge_workspace:desk',
    ])
  })

  it('prepares one immutable operation command and reuses it across a retry', async () => {
    const client = queryClient({ retry: 1 })
    const invalidateQueries = vi.spyOn(client, 'invalidateQueries')
    const randomUUID = vi.spyOn(crypto, 'randomUUID')
      .mockReturnValue('11111111-1111-4111-8111-111111111111')
    vi.mocked(knowledgeNavigationApi.createBookmark)
      .mockRejectedValueOnce(new Error('transient'))
      .mockResolvedValueOnce({ id: 'knowledge_bookmark:one' } as never)
    const { result } = renderHook(() => useCreateKnowledgeBookmark(), {
      wrapper: wrapperFor(client),
    })
    const input = {
      target: { kind: 'document' as const, documentId: 'knowledge_engine_document:one' },
      displayLabel: 'One', authorityKind: null, spaceId: null, folderId: null,
      tags: [], position: 0,
    }

    await act(async () => { await result.current.mutateAsync(input) })

    expect(randomUUID).toHaveBeenCalledTimes(1)
    expect(knowledgeNavigationApi.createBookmark).toHaveBeenCalledTimes(2)
    const first = vi.mocked(knowledgeNavigationApi.createBookmark).mock.calls[0][0]
    const second = vi.mocked(knowledgeNavigationApi.createBookmark).mock.calls[1][0]
    expect(second).toBe(first)
    expect(first.operationId).toBe('11111111-1111-4111-8111-111111111111')
    expect(Object.isFrozen(first)).toBe(true)
    expect(input).not.toHaveProperty('operationId')
    expect(invalidateQueries).toHaveBeenCalledTimes(1)
    expect(invalidateQueries).toHaveBeenCalledWith({
      queryKey: knowledgeNavigationKeys.bookmarksRoot,
    })
  })

  it('invalidates only the folder collection after a folder mutation', async () => {
    const client = queryClient()
    const invalidateQueries = vi.spyOn(client, 'invalidateQueries')
    vi.spyOn(crypto, 'randomUUID')
      .mockReturnValue('22222222-2222-4222-8222-222222222222')
    vi.mocked(knowledgeNavigationApi.createFolder)
      .mockResolvedValue({ id: 'knowledge_bookmark_folder:research' } as never)
    const { result } = renderHook(() => useCreateKnowledgeFolder(), {
      wrapper: wrapperFor(client),
    })

    await act(async () => {
      await result.current.mutateAsync({ name: 'Research', parentFolderId: null, position: 0 })
    })

    expect(invalidateQueries).toHaveBeenCalledTimes(1)
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: knowledgeNavigationKeys.folders })
  })

  it('invalidates only the workspace collection after a workspace mutation', async () => {
    const client = queryClient()
    const invalidateQueries = vi.spyOn(client, 'invalidateQueries')
    vi.spyOn(crypto, 'randomUUID')
      .mockReturnValue('33333333-3333-4333-8333-333333333333')
    vi.mocked(knowledgeNavigationApi.deleteWorkspace).mockResolvedValue({} as never)
    const { result } = renderHook(() => useDeleteKnowledgeWorkspace(), {
      wrapper: wrapperFor(client),
    })

    await act(async () => {
      await result.current.mutateAsync({
        workspaceId: 'named_knowledge_workspace:desk', command: { expectedRevision: 2 },
      })
    })

    expect(invalidateQueries).toHaveBeenCalledTimes(1)
    expect(invalidateQueries).toHaveBeenCalledWith({
      queryKey: knowledgeNavigationKeys.workspaces,
    })
  })

  it('keeps restore-plan and Random Note explicit and side-effect free on mount', async () => {
    const client = queryClient()
    vi.mocked(knowledgeNavigationApi.restorePlan).mockResolvedValue({} as never)
    vi.mocked(knowledgeNavigationApi.randomNote)
      .mockResolvedValue({ state: 'empty', document: null })
    const restore = renderHook(() => useRestoreKnowledgeWorkspace(), {
      wrapper: wrapperFor(client),
    })
    const random = renderHook(() => useRandomKnowledgeNote(), {
      wrapper: wrapperFor(client),
    })

    expect(knowledgeNavigationApi.restorePlan).not.toHaveBeenCalled()
    expect(knowledgeNavigationApi.randomNote).not.toHaveBeenCalled()

    await act(async () => {
      await restore.result.current.mutateAsync({
        workspaceId: 'named_knowledge_workspace:desk', revision: 2,
      })
      await random.result.current.mutateAsync({ tags: ['Evidence'] })
    })

    await waitFor(() => {
      expect(knowledgeNavigationApi.restorePlan).toHaveBeenCalledWith(
        'named_knowledge_workspace:desk', 2,
      )
      expect(knowledgeNavigationApi.randomNote).toHaveBeenCalledWith({ tags: ['Evidence'] })
    })
  })
})
