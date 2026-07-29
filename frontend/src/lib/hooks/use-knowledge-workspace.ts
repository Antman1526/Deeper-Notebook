'use client'

import { useEffect, useRef, useSyncExternalStore } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'

import {
  knowledgeWorkspaceApi,
  serializeKnowledgeWorkspace,
  type KnowledgeWorkspaceDocument,
} from '@/lib/api/knowledge-workspace'
import {
  getKnowledgeWorkspaceRevision,
  useKnowledgeWorkspaceStore,
  type KnowledgeWorkspaceState,
} from '@/lib/stores/knowledge-workspace-store'

export const knowledgeWorkspaceKeys = {
  document: ['knowledge-workspace'] as const,
}

function selectSerializableWorkspace(
  state: KnowledgeWorkspaceState,
): KnowledgeWorkspaceDocument {
  return {
    version: state.version,
    panes: state.panes,
    layout: state.layout,
    activePaneId: state.activePaneId,
    nextId: state.nextId,
  }
}

function validatedSnapshot(state: KnowledgeWorkspaceState): {
  ok: true
  document: KnowledgeWorkspaceDocument
  fingerprint: string
  revision: number
} | {
  ok: false
  error: Error
} {
  const document = selectSerializableWorkspace(state)
  try {
    return {
      ok: true,
      document,
      fingerprint: JSON.stringify(serializeKnowledgeWorkspace(document)),
      revision: state.revision,
    }
  } catch (cause) {
    const detail = cause instanceof Error ? cause.message : 'unknown validation failure'
    return {
      ok: false,
      error: new Error(`Invalid workspace snapshot: ${detail}`),
    }
  }
}

type ValidWorkspaceSnapshot = Extract<
  ReturnType<typeof validatedSnapshot>,
  { ok: true }
>

interface PersistenceStatus {
  error: Error | null
  isError: boolean
  isPending: boolean
  isSuccess: boolean
  status: 'idle' | 'pending' | 'error' | 'success'
}

interface WorkspaceFlushResult {
  ok: boolean
  error?: string
}

type SaveExecutor = (
  document: KnowledgeWorkspaceDocument,
) => Promise<KnowledgeWorkspaceDocument>

interface PersistenceCoordinator {
  consumers: number
  executor: SaveExecutor | null
  inFlightSnapshot: ValidWorkspaceSnapshot | null
  queuedSnapshot: ValidWorkspaceSnapshot | null
  debouncedSnapshot: ValidWorkspaceSnapshot | null
  timer: ReturnType<typeof setTimeout> | null
  storeUnsubscribe: (() => void) | null
  listeners: Set<() => void>
  flushWaiters: Set<(result: WorkspaceFlushResult) => void>
  status: PersistenceStatus
  hasSucceeded: boolean
}

const idlePersistenceStatus: PersistenceStatus = {
  error: null,
  isError: false,
  isPending: false,
  isSuccess: false,
  status: 'idle',
}

const persistenceCoordinator: PersistenceCoordinator = {
  consumers: 0,
  executor: null,
  inFlightSnapshot: null,
  queuedSnapshot: null,
  debouncedSnapshot: null,
  timer: null,
  storeUnsubscribe: null,
  listeners: new Set(),
  flushWaiters: new Set(),
  status: idlePersistenceStatus,
  hasSucceeded: false,
}

const persistenceCoordinatorTestResetKey =
  '__DEEPER_NOTEBOOK_KNOWLEDGE_WORKSPACE_TEST_RESET__'
const desktopWorkspaceFlushKey =
  'DEEPER_NOTEBOOK_FLUSH_KNOWLEDGE_WORKSPACE'

function preferLatest(
  current: ValidWorkspaceSnapshot | null,
  candidate: ValidWorkspaceSnapshot,
): ValidWorkspaceSnapshot {
  if (
    !current
    || candidate.revision > current.revision
    || (
      candidate.revision === current.revision
      && candidate.fingerprint !== current.fingerprint
    )
  ) {
    return candidate
  }
  return current
}

function isSnapshotDurable(
  snapshot: ValidWorkspaceSnapshot,
  state: KnowledgeWorkspaceState,
): boolean {
  return (
    snapshot.revision < state.durableRevision
    || (
      snapshot.revision === state.durableRevision
      && snapshot.fingerprint === state.durableFingerprint
    )
  )
}

function coordinatorHasPendingWork(): boolean {
  return Boolean(
    persistenceCoordinator.inFlightSnapshot
    || persistenceCoordinator.queuedSnapshot
    || persistenceCoordinator.debouncedSnapshot
    || persistenceCoordinator.timer,
  )
}

function settleFlushWaitersIfIdle(): void {
  if (
    coordinatorHasPendingWork()
    || persistenceCoordinator.flushWaiters.size === 0
  ) {
    return
  }
  const error = persistenceCoordinator.status.error
  const result: WorkspaceFlushResult = error
    ? { ok: false, error: error.message }
    : { ok: true }
  const waiters = [...persistenceCoordinator.flushWaiters]
  persistenceCoordinator.flushWaiters.clear()
  waiters.forEach((resolve) => resolve(result))
}

function publishPersistenceStatus(error = persistenceCoordinator.status.error): void {
  const isPending = coordinatorHasPendingWork()
  const nextStatus: PersistenceStatus = {
    error,
    isError: Boolean(error),
    isPending,
    isSuccess: !error && !isPending && persistenceCoordinator.hasSucceeded,
    status: error
      ? 'error'
      : isPending
        ? 'pending'
        : persistenceCoordinator.hasSucceeded
          ? 'success'
          : 'idle',
  }
  if (
    nextStatus.error === persistenceCoordinator.status.error
    && nextStatus.isPending === persistenceCoordinator.status.isPending
    && nextStatus.status === persistenceCoordinator.status.status
  ) {
    settleFlushWaitersIfIdle()
    return
  }
  persistenceCoordinator.status = nextStatus
  persistenceCoordinator.listeners.forEach((listener) => listener())
  settleFlushWaitersIfIdle()
}

function startCoordinatedSave(snapshot: ValidWorkspaceSnapshot): void {
  if (isSnapshotDurable(snapshot, useKnowledgeWorkspaceStore.getState())) return
  if (persistenceCoordinator.inFlightSnapshot) {
    persistenceCoordinator.queuedSnapshot = preferLatest(
      persistenceCoordinator.queuedSnapshot,
      snapshot,
    )
    publishPersistenceStatus()
    return
  }
  const executor = persistenceCoordinator.executor
  if (!executor) {
    persistenceCoordinator.queuedSnapshot = preferLatest(
      persistenceCoordinator.queuedSnapshot,
      snapshot,
    )
    publishPersistenceStatus()
    return
  }

  persistenceCoordinator.inFlightSnapshot = snapshot
  publishPersistenceStatus(null)
  void executor(snapshot.document)
    .then(() => {
      useKnowledgeWorkspaceStore
        .getState()
        .markWorkspaceDurable(snapshot.revision, snapshot.fingerprint)
      persistenceCoordinator.hasSucceeded = true
    })
    .catch((cause) => {
      const error = cause instanceof Error ? cause : new Error(String(cause))
      publishPersistenceStatus(error)
    })
    .finally(() => {
      persistenceCoordinator.inFlightSnapshot = null
      const next = persistenceCoordinator.queuedSnapshot
      persistenceCoordinator.queuedSnapshot = null
      if (next) {
        startCoordinatedSave(next)
        if (!coordinatorHasPendingWork()) publishPersistenceStatus()
      } else {
        publishPersistenceStatus()
      }
    })
}

function flushCoordinatedDebounce(): void {
  persistenceCoordinator.timer = null
  const snapshot = persistenceCoordinator.debouncedSnapshot
  persistenceCoordinator.debouncedSnapshot = null
  if (snapshot) startCoordinatedSave(snapshot)
  else publishPersistenceStatus()
}

function scheduleCoordinatedSave(snapshot: ValidWorkspaceSnapshot): void {
  if (persistenceCoordinator.inFlightSnapshot) {
    if (persistenceCoordinator.timer) {
      clearTimeout(persistenceCoordinator.timer)
      persistenceCoordinator.timer = null
    }
    persistenceCoordinator.debouncedSnapshot = null
    persistenceCoordinator.queuedSnapshot = preferLatest(
      persistenceCoordinator.queuedSnapshot,
      snapshot,
    )
    publishPersistenceStatus()
    return
  }

  persistenceCoordinator.debouncedSnapshot = preferLatest(
    persistenceCoordinator.debouncedSnapshot,
    snapshot,
  )
  if (persistenceCoordinator.timer) clearTimeout(persistenceCoordinator.timer)
  persistenceCoordinator.timer = setTimeout(flushCoordinatedDebounce, 400)
  publishPersistenceStatus(null)
}

function flushKnowledgeWorkspacePersistence(): Promise<WorkspaceFlushResult> {
  observeWorkspaceForPersistence(useKnowledgeWorkspaceStore.getState())
  if (persistenceCoordinator.timer) {
    clearTimeout(persistenceCoordinator.timer)
    flushCoordinatedDebounce()
  }
  if (!coordinatorHasPendingWork()) {
    const error = persistenceCoordinator.status.error
    return Promise.resolve(
      error ? { ok: false, error: error.message } : { ok: true },
    )
  }
  return new Promise((resolve) => {
    persistenceCoordinator.flushWaiters.add(resolve)
    settleFlushWaitersIfIdle()
  })
}

function observeWorkspaceForPersistence(state: KnowledgeWorkspaceState): void {
  if (!state.hydrated) return
  const snapshot = validatedSnapshot(state)
  if (!snapshot.ok) {
    const currentError = persistenceCoordinator.status.error
    publishPersistenceStatus(
      currentError?.message === snapshot.error.message ? currentError : snapshot.error,
    )
    return
  }
  if (isSnapshotDurable(snapshot, state)) {
    if (persistenceCoordinator.status.error?.message.startsWith('Invalid workspace snapshot:')) {
      publishPersistenceStatus(null)
    }
    return
  }
  publishPersistenceStatus(null)
  scheduleCoordinatedSave(snapshot)
}

function attachPersistenceConsumer(executor: SaveExecutor): () => void {
  persistenceCoordinator.executor = executor
  persistenceCoordinator.consumers += 1
  if (!persistenceCoordinator.storeUnsubscribe) {
    persistenceCoordinator.storeUnsubscribe =
      useKnowledgeWorkspaceStore.subscribe(observeWorkspaceForPersistence)
  }
  observeWorkspaceForPersistence(useKnowledgeWorkspaceStore.getState())

  return () => {
    persistenceCoordinator.consumers = Math.max(0, persistenceCoordinator.consumers - 1)
    if (persistenceCoordinator.consumers > 0) return
    persistenceCoordinator.storeUnsubscribe?.()
    persistenceCoordinator.storeUnsubscribe = null
    if (persistenceCoordinator.timer) {
      clearTimeout(persistenceCoordinator.timer)
      persistenceCoordinator.timer = null
    }
    const snapshot = persistenceCoordinator.debouncedSnapshot
    persistenceCoordinator.debouncedSnapshot = null
    if (snapshot) startCoordinatedSave(snapshot)
    else publishPersistenceStatus()
  }
}

function subscribePersistenceStatus(listener: () => void): () => void {
  persistenceCoordinator.listeners.add(listener)
  return () => persistenceCoordinator.listeners.delete(listener)
}

function getPersistenceStatus(): PersistenceStatus {
  return persistenceCoordinator.status
}

function resetKnowledgeWorkspacePersistenceCoordinatorForTests(): void {
  if (persistenceCoordinator.inFlightSnapshot) {
    throw new Error('cannot reset the workspace persistence coordinator while a save is active')
  }
  if (persistenceCoordinator.consumers > 0) {
    throw new Error('cannot reset the workspace persistence coordinator with active consumers')
  }
  if (persistenceCoordinator.timer) clearTimeout(persistenceCoordinator.timer)
  persistenceCoordinator.storeUnsubscribe?.()
  persistenceCoordinator.executor = null
  persistenceCoordinator.queuedSnapshot = null
  persistenceCoordinator.debouncedSnapshot = null
  persistenceCoordinator.timer = null
  persistenceCoordinator.storeUnsubscribe = null
  persistenceCoordinator.flushWaiters.clear()
  persistenceCoordinator.status = idlePersistenceStatus
  persistenceCoordinator.hasSucceeded = false
}

if (typeof window !== 'undefined') {
  Object.defineProperty(window, desktopWorkspaceFlushKey, {
    configurable: true,
    value: flushKnowledgeWorkspacePersistence,
  })
}

if (process.env.NODE_ENV === 'test') {
  Object.defineProperty(globalThis, persistenceCoordinatorTestResetKey, {
    configurable: true,
    value: resetKnowledgeWorkspacePersistenceCoordinatorForTests,
  })
}

export function useHydrateKnowledgeWorkspace() {
  const requestStartRevision = useRef(getKnowledgeWorkspaceRevision())
  const applied = useRef(false)
  const query = useQuery({
    queryKey: knowledgeWorkspaceKeys.document,
    queryFn: knowledgeWorkspaceApi.get,
    staleTime: Infinity,
  })

  useEffect(() => {
    if (!query.data || applied.current) return
    applied.current = true
    useKnowledgeWorkspaceStore
      .getState()
      .hydrateWorkspace(query.data, requestStartRevision.current)
  }, [query.data])

  return query
}

export function usePersistKnowledgeWorkspace() {
  const mutation = useMutation({
    mutationFn: knowledgeWorkspaceApi.put,
  })
  const status = useSyncExternalStore(
    subscribePersistenceStatus,
    getPersistenceStatus,
    getPersistenceStatus,
  )

  useEffect(() => {
    return attachPersistenceConsumer(mutation.mutateAsync)
  }, [mutation.mutateAsync])

  return status
}
