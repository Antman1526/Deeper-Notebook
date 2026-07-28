import type { ReactNode } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/lib/api/knowledge-workspace', async (importOriginal) => {
  const original = await importOriginal<typeof import('@/lib/api/knowledge-workspace')>()
  return {
    ...original,
    knowledgeWorkspaceApi: {
      get: vi.fn(),
      put: vi.fn(),
    },
  }
})

import {
  defaultKnowledgeWorkspace,
  knowledgeWorkspaceApi,
  type KnowledgeWorkspaceDocument,
} from '@/lib/api/knowledge-workspace'
import { useKnowledgeWorkspaceStore } from '@/lib/stores/knowledge-workspace-store'
import {
  useHydrateKnowledgeWorkspace,
  usePersistKnowledgeWorkspace,
} from './use-knowledge-workspace'

const originalReplaceWorkspace = useKnowledgeWorkspaceStore.getState().replaceWorkspace

const plan = {
  vaultId: 'vault:one',
  noteId: 'note:plan',
  title: 'Plan',
  relativePath: 'Projects/Plan.md',
} as const

function remoteWorkspace(): KnowledgeWorkspaceDocument {
  return {
    version: 1,
    activePaneId: 'pane-1',
    nextId: 8,
    panes: {
      'pane-1': {
        id: 'pane-1',
        activeTabId: 'tab-7',
        tabs: [{
          id: 'tab-7',
          ...plan,
          viewMode: 'live-preview',
        }],
      },
    },
    layout: { type: 'pane', paneId: 'pane-1' },
  }
}

function createWrapper() {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  })
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>
  }
}

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason: unknown) => void
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise
    reject = rejectPromise
  })
  return { promise, resolve, reject }
}

describe('knowledge workspace synchronization', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useKnowledgeWorkspaceStore.getState().resetWorkspace()
  })

  afterEach(() => {
    useKnowledgeWorkspaceStore.setState({ replaceWorkspace: originalReplaceWorkspace })
    vi.useRealTimers()
  })

  it('hydrates from GET exactly once and marks the immediate store hydrated', async () => {
    vi.mocked(knowledgeWorkspaceApi.get).mockResolvedValue(remoteWorkspace())
    const replaceWorkspace = vi.fn(
      useKnowledgeWorkspaceStore.getState().replaceWorkspace,
    )
    useKnowledgeWorkspaceStore.setState({ replaceWorkspace })

    const { rerender } = renderHook(
      () => useHydrateKnowledgeWorkspace(),
      { wrapper: createWrapper() },
    )

    await waitFor(() => {
      expect(useKnowledgeWorkspaceStore.getState()).toMatchObject({
        hydrated: true,
        activePaneId: 'pane-1',
        nextId: 8,
      })
    })
    expect(replaceWorkspace).toHaveBeenCalledTimes(1)
    expect(knowledgeWorkspaceApi.get).toHaveBeenCalledTimes(1)

    rerender()
    expect(replaceWorkspace).toHaveBeenCalledTimes(1)
  })

  it('does not let a late GET overwrite user changes made after the request starts', async () => {
    const request = deferred<KnowledgeWorkspaceDocument>()
    vi.mocked(knowledgeWorkspaceApi.get).mockReturnValue(request.promise)
    renderHook(() => useHydrateKnowledgeWorkspace(), { wrapper: createWrapper() })

    act(() => {
      useKnowledgeWorkspaceStore.getState().openTab(plan)
    })
    await act(async () => {
      request.resolve(remoteWorkspace())
      await request.promise
    })

    await waitFor(() => expect(useKnowledgeWorkspaceStore.getState().hydrated).toBe(true))
    expect(useKnowledgeWorkspaceStore.getState().panes['pane-1'].tabs).toHaveLength(1)
    expect(useKnowledgeWorkspaceStore.getState().panes['pane-1'].tabs[0]).toMatchObject({
      ...plan,
      viewMode: 'reading',
    })
  })

  it('debounces a post-hydration state change into one PUT after 400 ms', async () => {
    vi.useFakeTimers()
    const initial = defaultKnowledgeWorkspace()
    useKnowledgeWorkspaceStore.getState().replaceWorkspace(initial)
    vi.mocked(knowledgeWorkspaceApi.put).mockImplementation(async (document) => document)
    renderHook(() => usePersistKnowledgeWorkspace(), { wrapper: createWrapper() })

    act(() => {
      useKnowledgeWorkspaceStore.getState().openTab(plan)
    })
    await act(async () => {
      await vi.advanceTimersByTimeAsync(399)
    })
    expect(knowledgeWorkspaceApi.put).not.toHaveBeenCalled()

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1)
    })
    expect(knowledgeWorkspaceApi.put).toHaveBeenCalledTimes(1)
    expect(knowledgeWorkspaceApi.put).toHaveBeenCalledWith(expect.objectContaining({
      version: 1,
      activePaneId: 'pane-1',
      nextId: 3,
    }))
  })

  it('does not echo the initial GET hydration back through PUT', async () => {
    vi.useFakeTimers()
    vi.mocked(knowledgeWorkspaceApi.get).mockResolvedValue(remoteWorkspace())
    vi.mocked(knowledgeWorkspaceApi.put).mockImplementation(async (document) => document)
    renderHook(() => {
      const hydration = useHydrateKnowledgeWorkspace()
      const persistence = usePersistKnowledgeWorkspace()
      return { hydration, persistence }
    }, { wrapper: createWrapper() })

    await act(async () => {
      await vi.runAllTimersAsync()
    })
    expect(useKnowledgeWorkspaceStore.getState().hydrated).toBe(true)
    expect(knowledgeWorkspaceApi.put).not.toHaveBeenCalled()
  })

  it('retains local state and exposes the error when PUT fails', async () => {
    vi.useFakeTimers()
    useKnowledgeWorkspaceStore.getState().replaceWorkspace(defaultKnowledgeWorkspace())
    const saveError = new Error('disk unavailable')
    vi.mocked(knowledgeWorkspaceApi.put).mockRejectedValue(saveError)
    const { result } = renderHook(
      () => usePersistKnowledgeWorkspace(),
      { wrapper: createWrapper() },
    )

    act(() => {
      useKnowledgeWorkspaceStore.getState().openTab(plan)
    })
    await act(async () => {
      await vi.advanceTimersByTimeAsync(400)
      await vi.runAllTimersAsync()
    })

    expect(result.current.error).toBe(saveError)
    expect(useKnowledgeWorkspaceStore.getState().panes['pane-1'].tabs[0])
      .toMatchObject(plan)
  })

  it('flushes pending valid state with mutateAsync on unmount without sendBeacon', async () => {
    vi.useFakeTimers()
    useKnowledgeWorkspaceStore.getState().replaceWorkspace(defaultKnowledgeWorkspace())
    vi.mocked(knowledgeWorkspaceApi.put).mockImplementation(async (document) => document)
    const sendBeacon = vi.fn()
    Object.defineProperty(navigator, 'sendBeacon', {
      configurable: true,
      value: sendBeacon,
    })
    const { unmount } = renderHook(
      () => usePersistKnowledgeWorkspace(),
      { wrapper: createWrapper() },
    )

    act(() => {
      useKnowledgeWorkspaceStore.getState().openTab(plan)
    })
    unmount()
    await act(async () => {
      await vi.runAllTimersAsync()
    })

    expect(knowledgeWorkspaceApi.put).toHaveBeenCalledTimes(1)
    expect(sendBeacon).not.toHaveBeenCalled()
  })
})
