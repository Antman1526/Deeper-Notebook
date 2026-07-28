'use client'

import { useEffect, useRef } from 'react'
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
  document: KnowledgeWorkspaceDocument
  fingerprint: string
} | null {
  const document = selectSerializableWorkspace(state)
  try {
    return {
      document,
      fingerprint: JSON.stringify(serializeKnowledgeWorkspace(document)),
    }
  } catch {
    return null
  }
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
    if (getKnowledgeWorkspaceRevision() === requestStartRevision.current) {
      useKnowledgeWorkspaceStore.getState().replaceWorkspace(query.data)
    } else {
      useKnowledgeWorkspaceStore.setState({ hydrated: true })
    }
  }, [query.data])

  return query
}

export function usePersistKnowledgeWorkspace() {
  const mutation = useMutation({
    mutationFn: knowledgeWorkspaceApi.put,
  })
  const mutateAsync = mutation.mutateAsync

  useEffect(() => {
    const initialState = useKnowledgeWorkspaceStore.getState()
    const initialRevision = getKnowledgeWorkspaceRevision()
    let wasHydrated = initialState.hydrated
    let lastFingerprint = validatedSnapshot(initialState)?.fingerprint ?? null
    let pendingDocument: KnowledgeWorkspaceDocument | null = null
    let timer: ReturnType<typeof setTimeout> | null = null

    const sendPending = () => {
      timer = null
      const document = pendingDocument
      pendingDocument = null
      if (!document) return
      void mutateAsync(document).catch(() => undefined)
    }

    const schedule = (document: KnowledgeWorkspaceDocument) => {
      pendingDocument = document
      if (timer) clearTimeout(timer)
      timer = setTimeout(sendPending, 400)
    }

    const unsubscribe = useKnowledgeWorkspaceStore.subscribe((state) => {
      if (!state.hydrated) {
        wasHydrated = false
        return
      }

      const snapshot = validatedSnapshot(state)
      if (!snapshot) return

      if (!wasHydrated) {
        wasHydrated = true
        lastFingerprint = snapshot.fingerprint
        if (getKnowledgeWorkspaceRevision() !== initialRevision) {
          schedule(snapshot.document)
        }
        return
      }

      if (snapshot.fingerprint === lastFingerprint) return
      lastFingerprint = snapshot.fingerprint
      schedule(snapshot.document)
    })

    return () => {
      unsubscribe()
      if (timer) clearTimeout(timer)
      if (pendingDocument) {
        const document = pendingDocument
        pendingDocument = null
        void mutateAsync(document).catch(() => undefined)
      }
    }
  }, [mutateAsync])

  return mutation
}
