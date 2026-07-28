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
  serializeKnowledgeWorkspace,
  type KnowledgeWorkspaceDocument,
} from '@/lib/api/knowledge-workspace'
import { useKnowledgeWorkspaceStore } from '@/lib/stores/knowledge-workspace-store'
import {
  useHydrateKnowledgeWorkspace,
  usePersistKnowledgeWorkspace,
} from './use-knowledge-workspace'
import * as knowledgeWorkspaceHooks from './use-knowledge-workspace'

const originalReplaceWorkspace = useKnowledgeWorkspaceStore.getState().replaceWorkspace
const originalHydrateWorkspace = useKnowledgeWorkspaceStore.getState().hydrateWorkspace
const persistenceCoordinatorTestResetKey =
  '__DEEPER_NOTEBOOK_KNOWLEDGE_WORKSPACE_TEST_RESET__'

function resetKnowledgeWorkspacePersistenceCoordinatorForTests(): void {
  const testGlobal = globalThis as typeof globalThis & {
    [persistenceCoordinatorTestResetKey]?: () => void
  }
  const reset = testGlobal[persistenceCoordinatorTestResetKey]
  if (!reset) {
    throw new Error('workspace persistence test reset is unavailable')
  }
  reset()
}

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
    resetKnowledgeWorkspacePersistenceCoordinatorForTests()
    vi.clearAllMocks()
    useKnowledgeWorkspaceStore.getState().resetWorkspace()
  })

  afterEach(() => {
    useKnowledgeWorkspaceStore.setState({
      replaceWorkspace: originalReplaceWorkspace,
      hydrateWorkspace: originalHydrateWorkspace,
    })
    vi.useRealTimers()
  })

  it('does not expose coordinator test controls from the production module', () => {
    expect(knowledgeWorkspaceHooks)
      .not.toHaveProperty('resetKnowledgeWorkspacePersistenceCoordinatorForTests')
  })

  it('hydrates from GET exactly once and marks the immediate store hydrated', async () => {
    vi.mocked(knowledgeWorkspaceApi.get).mockResolvedValue(remoteWorkspace())
    const hydrateWorkspace = vi.fn(
      useKnowledgeWorkspaceStore.getState().hydrateWorkspace,
    )
    useKnowledgeWorkspaceStore.setState({ hydrateWorkspace })

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
    expect(hydrateWorkspace).toHaveBeenCalledTimes(1)
    expect(useKnowledgeWorkspaceStore.getState().durableRevision)
      .toBe(useKnowledgeWorkspaceStore.getState().revision)
    expect(knowledgeWorkspaceApi.get).toHaveBeenCalledTimes(1)

    rerender()
    expect(hydrateWorkspace).toHaveBeenCalledTimes(1)
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
    expect(useKnowledgeWorkspaceStore.getState().revision)
      .toBeGreaterThan(useKnowledgeWorkspaceStore.getState().durableRevision)
  })

  it('persists a pre-hydration edit even when persistence mounts after hydration', async () => {
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
    expect(useKnowledgeWorkspaceStore.getState().revision)
      .toBeGreaterThan(useKnowledgeWorkspaceStore.getState().durableRevision)

    vi.useFakeTimers()
    vi.mocked(knowledgeWorkspaceApi.put).mockImplementation(async (document) => document)
    renderHook(() => usePersistKnowledgeWorkspace(), { wrapper: createWrapper() })
    await act(async () => {
      await vi.advanceTimersByTimeAsync(400)
    })

    expect(knowledgeWorkspaceApi.put).toHaveBeenCalledTimes(1)
    expect(knowledgeWorkspaceApi.put).toHaveBeenCalledWith(expect.objectContaining({
      panes: {
        'pane-1': expect.objectContaining({
          tabs: [expect.objectContaining(plan)],
        }),
      },
    }))
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

  it('serializes and coalesces an in-flight save with the newest unmount snapshot', async () => {
    vi.useFakeTimers()
    useKnowledgeWorkspaceStore.getState().replaceWorkspace(defaultKnowledgeWorkspace())
    const firstSave = deferred<KnowledgeWorkspaceDocument>()
    const secondSave = deferred<KnowledgeWorkspaceDocument>()
    let activeSaves = 0
    let maxActiveSaves = 0
    vi.mocked(knowledgeWorkspaceApi.put).mockImplementation(() => {
      activeSaves += 1
      maxActiveSaves = Math.max(maxActiveSaves, activeSaves)
      const save = vi.mocked(knowledgeWorkspaceApi.put).mock.calls.length === 1
        ? firstSave
        : secondSave
      return save.promise.finally(() => {
        activeSaves -= 1
      })
    })
    const { unmount } = renderHook(
      () => usePersistKnowledgeWorkspace(),
      { wrapper: createWrapper() },
    )

    act(() => {
      useKnowledgeWorkspaceStore.getState().openTab(plan)
    })
    await act(async () => {
      await vi.advanceTimersByTimeAsync(400)
    })
    expect(knowledgeWorkspaceApi.put).toHaveBeenCalledTimes(1)

    const activeTabId = useKnowledgeWorkspaceStore
      .getState().panes['pane-1'].activeTabId!
    act(() => {
      useKnowledgeWorkspaceStore
        .getState().setTabViewMode('pane-1', activeTabId, 'graph')
    })
    unmount()

    expect(knowledgeWorkspaceApi.put).toHaveBeenCalledTimes(1)
    expect(maxActiveSaves).toBe(1)

    await act(async () => {
      firstSave.resolve(vi.mocked(knowledgeWorkspaceApi.put).mock.calls[0][0])
      await firstSave.promise
      await vi.runAllTimersAsync()
    })
    expect(knowledgeWorkspaceApi.put).toHaveBeenCalledTimes(2)
    expect(maxActiveSaves).toBe(1)
    expect(vi.mocked(knowledgeWorkspaceApi.put).mock.calls[1][0]
      .panes['pane-1'].tabs[0].viewMode).toBe('graph')

    await act(async () => {
      secondSave.resolve(vi.mocked(knowledgeWorkspaceApi.put).mock.calls[1][0])
      await secondSave.promise
      await vi.runAllTimersAsync()
    })
    expect(useKnowledgeWorkspaceStore.getState().durableRevision)
      .toBe(useKnowledgeWorkspaceStore.getState().revision)
  })

  it('shares one save queue across Strict Mode effect cleanup and re-setup', async () => {
    vi.useFakeTimers()
    useKnowledgeWorkspaceStore.getState().replaceWorkspace(defaultKnowledgeWorkspace())
    useKnowledgeWorkspaceStore.getState().openTab(plan)
    const firstSave = deferred<KnowledgeWorkspaceDocument>()
    const secondSave = deferred<KnowledgeWorkspaceDocument>()
    let activeSaves = 0
    let maxActiveSaves = 0
    vi.mocked(knowledgeWorkspaceApi.put).mockImplementation(() => {
      activeSaves += 1
      maxActiveSaves = Math.max(maxActiveSaves, activeSaves)
      const save = vi.mocked(knowledgeWorkspaceApi.put).mock.calls.length === 1
        ? firstSave
        : secondSave
      return save.promise.finally(() => {
        activeSaves -= 1
      })
    })

    renderHook(
      () => usePersistKnowledgeWorkspace(),
      { wrapper: createWrapper(), reactStrictMode: true },
    )
    await act(async () => {
      await vi.advanceTimersByTimeAsync(400)
    })

    expect(knowledgeWorkspaceApi.put).toHaveBeenCalledTimes(1)
    expect(maxActiveSaves).toBe(1)

    await act(async () => {
      firstSave.resolve(vi.mocked(knowledgeWorkspaceApi.put).mock.calls[0][0])
      await firstSave.promise
      await vi.runAllTimersAsync()
    })
    if (vi.mocked(knowledgeWorkspaceApi.put).mock.calls.length === 2) {
      secondSave.resolve(vi.mocked(knowledgeWorkspaceApi.put).mock.calls[1][0])
      await act(async () => {
        await secondSave.promise
        await vi.runAllTimersAsync()
      })
    }
    expect(maxActiveSaves).toBe(1)
  })

  it('shares one save queue across a real unmount and fresh persistence mount', async () => {
    vi.useFakeTimers()
    useKnowledgeWorkspaceStore.getState().replaceWorkspace(defaultKnowledgeWorkspace())
    const firstSave = deferred<KnowledgeWorkspaceDocument>()
    const secondSave = deferred<KnowledgeWorkspaceDocument>()
    let activeSaves = 0
    let maxActiveSaves = 0
    vi.mocked(knowledgeWorkspaceApi.put).mockImplementation(() => {
      activeSaves += 1
      maxActiveSaves = Math.max(maxActiveSaves, activeSaves)
      const save = vi.mocked(knowledgeWorkspaceApi.put).mock.calls.length === 1
        ? firstSave
        : secondSave
      return save.promise.finally(() => {
        activeSaves -= 1
      })
    })
    const firstConsumer = renderHook(
      () => usePersistKnowledgeWorkspace(),
      { wrapper: createWrapper() },
    )

    act(() => {
      useKnowledgeWorkspaceStore.getState().openTab(plan)
    })
    await act(async () => {
      await vi.advanceTimersByTimeAsync(400)
    })
    expect(knowledgeWorkspaceApi.put).toHaveBeenCalledTimes(1)
    firstConsumer.unmount()

    const activeTabId = useKnowledgeWorkspaceStore
      .getState().panes['pane-1'].activeTabId!
    act(() => {
      useKnowledgeWorkspaceStore
        .getState().setTabViewMode('pane-1', activeTabId, 'graph')
    })
    renderHook(
      () => usePersistKnowledgeWorkspace(),
      { wrapper: createWrapper() },
    )
    await act(async () => {
      await vi.advanceTimersByTimeAsync(400)
    })

    expect(knowledgeWorkspaceApi.put).toHaveBeenCalledTimes(1)
    expect(maxActiveSaves).toBe(1)

    await act(async () => {
      firstSave.resolve(vi.mocked(knowledgeWorkspaceApi.put).mock.calls[0][0])
      await firstSave.promise
      await vi.runAllTimersAsync()
    })
    expect(knowledgeWorkspaceApi.put).toHaveBeenCalledTimes(2)
    expect(maxActiveSaves).toBe(1)
    expect(vi.mocked(knowledgeWorkspaceApi.put).mock.calls[1][0]
      .panes['pane-1'].tabs[0].viewMode).toBe('graph')

    await act(async () => {
      secondSave.resolve(vi.mocked(knowledgeWorkspaceApi.put).mock.calls[1][0])
      await secondSave.promise
      await vi.runAllTimersAsync()
    })
  })

  it('shares one save queue between simultaneous persistence consumers', async () => {
    vi.useFakeTimers()
    useKnowledgeWorkspaceStore.getState().replaceWorkspace(defaultKnowledgeWorkspace())
    const firstSave = deferred<KnowledgeWorkspaceDocument>()
    const secondSave = deferred<KnowledgeWorkspaceDocument>()
    let activeSaves = 0
    let maxActiveSaves = 0
    vi.mocked(knowledgeWorkspaceApi.put).mockImplementation(() => {
      activeSaves += 1
      maxActiveSaves = Math.max(maxActiveSaves, activeSaves)
      const save = vi.mocked(knowledgeWorkspaceApi.put).mock.calls.length === 1
        ? firstSave
        : secondSave
      return save.promise.finally(() => {
        activeSaves -= 1
      })
    })
    const firstConsumer = renderHook(
      () => usePersistKnowledgeWorkspace(),
      { wrapper: createWrapper() },
    )
    const secondConsumer = renderHook(
      () => usePersistKnowledgeWorkspace(),
      { wrapper: createWrapper() },
    )

    act(() => {
      useKnowledgeWorkspaceStore.getState().openTab(plan)
    })
    await act(async () => {
      await vi.advanceTimersByTimeAsync(400)
    })

    expect(knowledgeWorkspaceApi.put).toHaveBeenCalledTimes(1)
    expect(maxActiveSaves).toBe(1)
    expect(firstConsumer.result.current.isPending).toBe(true)
    expect(secondConsumer.result.current.isPending).toBe(true)

    const activeTabId = useKnowledgeWorkspaceStore
      .getState().panes['pane-1'].activeTabId!
    act(() => {
      useKnowledgeWorkspaceStore
        .getState().setTabViewMode('pane-1', activeTabId, 'graph')
    })
    await act(async () => {
      firstSave.resolve(vi.mocked(knowledgeWorkspaceApi.put).mock.calls[0][0])
      await firstSave.promise
      await vi.runAllTimersAsync()
    })
    expect(knowledgeWorkspaceApi.put).toHaveBeenCalledTimes(2)
    expect(vi.mocked(knowledgeWorkspaceApi.put).mock.calls[1][0]
      .panes['pane-1'].tabs[0].viewMode).toBe('graph')
    await act(async () => {
      secondSave.resolve(vi.mocked(knowledgeWorkspaceApi.put).mock.calls[1][0])
      await secondSave.promise
      await vi.runAllTimersAsync()
    })
    expect(maxActiveSaves).toBe(1)
  })

  it('persists a newer fingerprint that shares the in-flight snapshot revision', async () => {
    vi.useFakeTimers()
    useKnowledgeWorkspaceStore.getState().replaceWorkspace(defaultKnowledgeWorkspace())
    const firstSave = deferred<KnowledgeWorkspaceDocument>()
    const secondSave = deferred<KnowledgeWorkspaceDocument>()
    vi.mocked(knowledgeWorkspaceApi.put)
      .mockReturnValueOnce(firstSave.promise)
      .mockReturnValueOnce(secondSave.promise)
    renderHook(
      () => usePersistKnowledgeWorkspace(),
      { wrapper: createWrapper() },
    )

    act(() => {
      useKnowledgeWorkspaceStore.getState().openTab(plan)
    })
    await act(async () => {
      await vi.advanceTimersByTimeAsync(400)
    })
    const savedRevision = useKnowledgeWorkspaceStore.getState().revision
    expect(knowledgeWorkspaceApi.put).toHaveBeenCalledTimes(1)

    const current = useKnowledgeWorkspaceStore.getState()
    useKnowledgeWorkspaceStore.setState({
      panes: {
        ...current.panes,
        'pane-1': {
          ...current.panes['pane-1'],
          tabs: current.panes['pane-1'].tabs.map((tab) => ({
            ...tab,
            viewMode: 'graph',
          })),
        },
      },
    })
    expect(useKnowledgeWorkspaceStore.getState().revision).toBe(savedRevision)

    await act(async () => {
      firstSave.resolve(vi.mocked(knowledgeWorkspaceApi.put).mock.calls[0][0])
      await firstSave.promise
      await vi.runAllTimersAsync()
    })

    expect(knowledgeWorkspaceApi.put).toHaveBeenCalledTimes(2)
    expect(vi.mocked(knowledgeWorkspaceApi.put).mock.calls[1][0]
      .panes['pane-1'].tabs[0].viewMode).toBe('graph')

    await act(async () => {
      secondSave.resolve(vi.mocked(knowledgeWorkspaceApi.put).mock.calls[1][0])
      await secondSave.promise
      await vi.runAllTimersAsync()
    })
    const finalState = useKnowledgeWorkspaceStore.getState()
    expect(finalState.durableRevision).toBe(finalState.revision)
    expect(finalState.durableFingerprint).toBe(
      JSON.stringify(serializeKnowledgeWorkspace(finalState)),
    )
  })

  it('exposes a stable validation error instead of silently dropping an invalid snapshot', async () => {
    useKnowledgeWorkspaceStore.getState().replaceWorkspace(defaultKnowledgeWorkspace())
    useKnowledgeWorkspaceStore.getState().openTab(plan)
    const state = useKnowledgeWorkspaceStore.getState()
    useKnowledgeWorkspaceStore.setState({
      panes: {
        ...state.panes,
        'pane-1': {
          ...state.panes['pane-1'],
          tabs: state.panes['pane-1'].tabs.map((tab) => ({
            ...tab,
            relativePath: '/Users/owner/secret.md',
          })),
        },
      },
    })
    const { result, rerender } = renderHook(
      () => usePersistKnowledgeWorkspace(),
      { wrapper: createWrapper() },
    )

    await waitFor(() => expect(result.current.error).toBeInstanceOf(Error))
    const validationError = result.current.error
    expect(validationError?.message).toMatch(/invalid workspace/i)
    rerender()
    expect(result.current.error).toBe(validationError)
    expect(knowledgeWorkspaceApi.put).not.toHaveBeenCalled()
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
