'use client'

import { useEffect, useRef, useState } from 'react'
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

interface SaveQueueState {
  inFlight: boolean
  queuedSnapshot: ValidWorkspaceSnapshot | null
  debouncedSnapshot: ValidWorkspaceSnapshot | null
  timer: ReturnType<typeof setTimeout> | null
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
  const [validationError, setValidationError] = useState<Error | null>(null)
  const mutation = useMutation({
    mutationFn: knowledgeWorkspaceApi.put,
  })
  const mutateAsyncRef = useRef(mutation.mutateAsync)
  const queueRef = useRef<SaveQueueState | null>(null)

  useEffect(() => {
    mutateAsyncRef.current = mutation.mutateAsync
  }, [mutation.mutateAsync])

  useEffect(() => {
    const queue = queueRef.current ?? {
      inFlight: false,
      queuedSnapshot: null,
      debouncedSnapshot: null,
      timer: null,
    }
    queueRef.current = queue
    let unmounted = false

    const preferLatest = (
      current: ValidWorkspaceSnapshot | null,
      candidate: ValidWorkspaceSnapshot,
    ): ValidWorkspaceSnapshot => {
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

    const startSave = (snapshot: ValidWorkspaceSnapshot) => {
      const state = useKnowledgeWorkspaceStore.getState()
      if (snapshot.revision <= state.durableRevision) {
        return
      }
      if (queue.inFlight) {
        queue.queuedSnapshot = preferLatest(queue.queuedSnapshot, snapshot)
        return
      }

      queue.inFlight = true
      void mutateAsyncRef.current(snapshot.document)
        .then(() => {
          useKnowledgeWorkspaceStore
            .getState()
            .markWorkspaceDurable(snapshot.revision)
        })
        .catch(() => undefined)
        .finally(() => {
          queue.inFlight = false
          const next = queue.queuedSnapshot
          queue.queuedSnapshot = null
          if (next) startSave(next)
        })
    }

    const flushDebounce = () => {
      queue.timer = null
      const snapshot = queue.debouncedSnapshot
      queue.debouncedSnapshot = null
      if (snapshot) startSave(snapshot)
    }

    const schedule = (snapshot: ValidWorkspaceSnapshot) => {
      if (queue.inFlight) {
        if (queue.timer) {
          clearTimeout(queue.timer)
          queue.timer = null
        }
        queue.debouncedSnapshot = null
        queue.queuedSnapshot = preferLatest(queue.queuedSnapshot, snapshot)
        return
      }

      queue.debouncedSnapshot = preferLatest(queue.debouncedSnapshot, snapshot)
      if (queue.timer) clearTimeout(queue.timer)
      queue.timer = setTimeout(flushDebounce, 400)
    }

    const observe = (state: KnowledgeWorkspaceState) => {
      if (!state.hydrated) return
      const snapshot = validatedSnapshot(state)
      if (!snapshot.ok) {
        if (!unmounted) {
          setValidationError((current) =>
            current?.message === snapshot.error.message ? current : snapshot.error)
        }
        return
      }
      if (!unmounted) setValidationError(null)
      if (snapshot.revision <= state.durableRevision) return
      schedule(snapshot)
    }

    const unsubscribe = useKnowledgeWorkspaceStore.subscribe(observe)
    observe(useKnowledgeWorkspaceStore.getState())

    return () => {
      unmounted = true
      unsubscribe()
      if (queue.timer) {
        clearTimeout(queue.timer)
        queue.timer = null
      }
      const snapshot = queue.debouncedSnapshot
      queue.debouncedSnapshot = null
      if (snapshot) {
        startSave(snapshot)
      }
    }
  }, [])

  return {
    ...mutation,
    error: validationError ?? mutation.error,
  }
}
