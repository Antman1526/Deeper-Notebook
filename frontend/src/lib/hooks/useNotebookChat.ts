'use client'

import { useState, useCallback, useEffect, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { getApiErrorMessage } from '@/lib/utils/error-handler'
import { useTranslation } from '@/lib/hooks/use-translation'
import { chatApi } from '@/lib/api/chat'
import { QUERY_KEYS } from '@/lib/api/query-client'
import {
  NotebookChatMessage,
  CreateNotebookChatSessionRequest,
  UpdateNotebookChatSessionRequest,
  SourceListResponse,
  NoteResponse
} from '@/lib/types/api'
import { ContextSelections } from '@/app/(dashboard)/notebooks/[id]/page'

interface UseNotebookChatParams {
  notebookId: string
  sources: SourceListResponse[]
  notes: NoteResponse[]
  contextSelections: ContextSelections
}

export function useNotebookChat({ notebookId, sources, notes, contextSelections }: UseNotebookChatParams) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null)
  const [messages, setMessages] = useState<NotebookChatMessage[]>([])
  const [isSending, setIsSending] = useState(false)
  const [tokenCount, setTokenCount] = useState<number>(0)
  const [charCount, setCharCount] = useState<number>(0)
  // Pending model override for when user changes model before a session exists
  const [pendingModelOverride, setPendingModelOverride] = useState<string | null>(null)

  // Fetch sessions for this notebook
  const {
    data: sessions = [],
    isLoading: loadingSessions,
    refetch: refetchSessions
  } = useQuery({
    queryKey: QUERY_KEYS.notebookChatSessions(notebookId),
    queryFn: () => chatApi.listSessions(notebookId),
    enabled: !!notebookId
  })

  // Fetch current session with messages
  const {
    data: currentSession,
    refetch: refetchCurrentSession
  } = useQuery({
    queryKey: QUERY_KEYS.notebookChatSession(currentSessionId!),
    queryFn: () => chatApi.getSession(currentSessionId!),
    enabled: !!notebookId && !!currentSessionId
  })

  // Update messages when current session changes
  useEffect(() => {
    if (currentSession?.messages) {
      setMessages(currentSession.messages)
    }
  }, [currentSession])

  // Auto-select most recent session when sessions are loaded
  useEffect(() => {
    if (sessions.length > 0 && !currentSessionId) {
      // Sessions are sorted by created date desc from API
      const mostRecentSession = sessions[0]
      setCurrentSessionId(mostRecentSession.id)
    }
  }, [sessions, currentSessionId])

  // Create session mutation
  const createSessionMutation = useMutation({
    mutationFn: (data: CreateNotebookChatSessionRequest) =>
      chatApi.createSession(data),
    onSuccess: (newSession) => {
      queryClient.invalidateQueries({
        queryKey: QUERY_KEYS.notebookChatSessions(notebookId)
      })
      setCurrentSessionId(newSession.id)
      toast.success(t('chat.sessionCreated'))
    },
    onError: (err: unknown) => {
      const error = err as { response?: { data?: { detail?: string } }, message?: string };
      toast.error(getApiErrorMessage(error.response?.data?.detail || error.message, (key) => t(key), 'apiErrors.failedToCreateSession'))
    }
  })

  // Update session mutation
  const updateSessionMutation = useMutation({
    mutationFn: ({ sessionId, data }: {
      sessionId: string
      data: UpdateNotebookChatSessionRequest
    }) => chatApi.updateSession(sessionId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: QUERY_KEYS.notebookChatSessions(notebookId)
      })
      queryClient.invalidateQueries({
        queryKey: QUERY_KEYS.notebookChatSession(currentSessionId!)
      })
      toast.success(t('chat.sessionUpdated'))
    },
    onError: (err: unknown) => {
      const error = err as { response?: { data?: { detail?: string } }, message?: string };
      toast.error(getApiErrorMessage(error.response?.data?.detail || error.message, (key) => t(key), 'apiErrors.failedToUpdateSession'))
    }
  })

  // Delete session mutation
  const deleteSessionMutation = useMutation({
    mutationFn: (sessionId: string) =>
      chatApi.deleteSession(sessionId),
    onSuccess: (_, deletedId) => {
      queryClient.invalidateQueries({
        queryKey: QUERY_KEYS.notebookChatSessions(notebookId)
      })
      // v0.7.34 — if the user deleted the session they're currently
      // in, jump directly to the next-best session instead of leaving
      // them in a transient null state. The auto-select effect at
      // line 65 would eventually pick one anyway, but only AFTER the
      // sessions query refetches — in the meantime ChatPanel renders
      // a blank "no session" state for a frame or two, scroll resets,
      // and the user sees a jarring flicker.
      if (currentSessionId === deletedId) {
        const next = sessions.find((s) => s.id !== deletedId)
        setCurrentSessionId(next?.id ?? null)
        setMessages([])
      }
      toast.success(t('chat.sessionDeleted'))
    },
    onError: (err: unknown) => {
      const error = err as { response?: { data?: { detail?: string } }, message?: string };
      toast.error(getApiErrorMessage(error.response?.data?.detail || error.message, (key) => t(key), 'apiErrors.failedToDeleteSession'))
    }
  })

  // Build context from sources and notes based on user selections.
  // v0.6.24 — no longer setState-s tokenCount/charCount internally.
  // The previous version did, but that created a race when called twice
  // concurrently (e.g. user rapidly toggling source inclusion modes):
  // the LAST setState to land could be the FIRST request to start, leaving
  // counts stuck on a stale intermediate value. State updates are now the
  // caller's responsibility — see the gated effect below.
  const buildContext = useCallback(async () => {
    const context_config: { sources: Record<string, string>, notes: Record<string, string> } = {
      sources: {},
      notes: {}
    }

    sources.forEach(source => {
      const mode = contextSelections.sources[source.id]
      if (mode === 'insights') {
        context_config.sources[source.id] = 'insights'
      } else if (mode === 'full') {
        context_config.sources[source.id] = 'full content'
      } else {
        context_config.sources[source.id] = 'not in'
      }
    })

    notes.forEach(note => {
      const mode = contextSelections.notes[note.id]
      if (mode === 'full') {
        context_config.notes[note.id] = 'full content'
      } else {
        context_config.notes[note.id] = 'not in'
      }
    })

    const response = await chatApi.buildContext({
      notebook_id: notebookId,
      context_config
    })
    return response  // { context, token_count, char_count }
  }, [notebookId, sources, notes, contextSelections])

  // Send message (synchronous, no streaming)
  const sendMessage = useCallback(async (message: string, modelOverride?: string) => {
    let sessionId = currentSessionId

    // Auto-create session if none exists
    if (!sessionId) {
      try {
        const defaultTitle = message.length > 30
          ? `${message.substring(0, 30)}...`
          : message
        const newSession = await chatApi.createSession({
          notebook_id: notebookId,
          title: defaultTitle,
          // Include pending model override when creating session
          model_override: pendingModelOverride ?? undefined
        })
        sessionId = newSession.id
        setCurrentSessionId(sessionId)
        // Clear pending model override now that it's applied to the session
        setPendingModelOverride(null)
        queryClient.invalidateQueries({
          queryKey: QUERY_KEYS.notebookChatSessions(notebookId)
        })
      } catch (err: unknown) {
        const error = err as { response?: { data?: { detail?: string } }, message?: string };
        toast.error(getApiErrorMessage(error.response?.data?.detail || error.message, (key) => t(key), 'apiErrors.failedToCreateSession'))
        return
      }
    }

    // v0.7.26 — generate a UNIQUE temp id per send via crypto.randomUUID()
    // instead of `temp-${Date.now()}`. Two issues with the timestamp
    // approach:
    //   1. Double-click within the same millisecond produced duplicate
    //      IDs — React key warnings, and a partial-failure scenario
    //      could wipe both messages.
    //   2. On error, the catch handler filtered *every* `temp-` message,
    //      so if send A succeeded then B was in-flight and C errored,
    //      the rollback removed B's optimistic copy too — the user
    //      saw their B vanish even though the server had it.
    // Now: each send gets its own UUID, and rollback only removes the
    // specific one this call created.
    const tempId = `temp-${(globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random()}`)}`
    const userMessage: NotebookChatMessage = {
      id: tempId,
      type: 'human',
      content: message,
      timestamp: new Date().toISOString()
    }
    setMessages(prev => [...prev, userMessage])
    setIsSending(true)

    try {
      // Build context and send message
      // v0.6.24 — buildContext now returns the whole response (context +
      // counts). We discard the counts here; they're set by the dedicated
      // effect that has the race-safe sequence guard. The actual context
      // string is what the API needs.
      const built = await buildContext()
      const response = await chatApi.sendMessage({
        session_id: sessionId,
        message,
        context: built.context,
        model_override: modelOverride ?? (currentSession?.model_override ?? undefined)
      })

      // Update messages with API response
      setMessages(response.messages)

      // Refetch current session to get updated data
      await refetchCurrentSession()
    } catch (err: unknown) {
      const error = err as { response?: { data?: { detail?: string } }, message?: string };
      console.error('Error sending message:', error)
      toast.error(getApiErrorMessage(error.response?.data?.detail || error.message, (key) => t(key), 'apiErrors.failedToSendMessage'))
      // v0.7.26 — remove ONLY this send's optimistic message, not every
      // temp- message in flight. See tempId comment above.
      setMessages(prev => prev.filter(msg => msg.id !== tempId))
    } finally {
      setIsSending(false)
    }
  }, [
    notebookId,
    currentSessionId,
    currentSession,
    pendingModelOverride,
    buildContext,
    refetchCurrentSession,
    queryClient,
    t
  ])

  // Switch session
  const switchSession = useCallback((sessionId: string) => {
    setCurrentSessionId(sessionId)
  }, [])

  // Create session
  const createSession = useCallback((title?: string) => {
    return createSessionMutation.mutate({
      notebook_id: notebookId,
      title
    })
  }, [createSessionMutation, notebookId])

  // Update session
  const updateSession = useCallback((sessionId: string, data: UpdateNotebookChatSessionRequest) => {
    return updateSessionMutation.mutate({
      sessionId,
      data
    })
  }, [updateSessionMutation])

  // Delete session
  const deleteSession = useCallback((sessionId: string) => {
    return deleteSessionMutation.mutate(sessionId)
  }, [deleteSessionMutation])

  // Set model override - handles both existing sessions and pending state
  const setModelOverride = useCallback((model: string | null) => {
    if (currentSessionId) {
      // Session exists - update it directly
      updateSessionMutation.mutate({
        sessionId: currentSessionId,
        data: { model_override: model }
      })
    } else {
      // No session yet - store as pending
      setPendingModelOverride(model)
    }
  }, [currentSessionId, updateSessionMutation])

  // v0.6.24 — fix a real out-of-order race when the user rapidly toggles
  // source/note inclusion. Each toggle triggers a new buildContext call,
  // and the previous effect simply awaited each and overwrote
  // tokenCount/charCount in completion order. Network latency varies, so
  // the LAST call to START was not always the LAST to FINISH — tokenCount
  // could end up stuck on a stale intermediate value (e.g. the user
  // selected A, A+B, A+B+C in fast succession, and the counts showed
  // the A+B total because that request finished last).
  //
  // Two guards:
  //   1. A monotonic request counter — each effect run captures its own
  //      counter, and only commits its result if its counter is STILL
  //      the most recent. Stale completions are dropped silently.
  //   2. A mountedRef — never setState after unmount.
  const contextRequestSeq = useRef(0)
  const mountedRef = useRef(true)
  useEffect(() => {
    mountedRef.current = true
    return () => { mountedRef.current = false }
  }, [])

  useEffect(() => {
    const mySeq = ++contextRequestSeq.current
    const updateContextCounts = async () => {
      try {
        const result = await buildContext()
        // Drop stale results. mySeq < contextRequestSeq.current means
        // another effect run started after us; its result will land
        // shortly and overwrite ours, so don't commit ours.
        if (!mountedRef.current || mySeq !== contextRequestSeq.current) return
        setTokenCount(result.token_count)
        setCharCount(result.char_count)
      } catch (error) {
        if (!mountedRef.current || mySeq !== contextRequestSeq.current) return
        console.error('Error updating context counts:', error)
      }
    }
    updateContextCounts()
  }, [buildContext])

  return {
    // State
    sessions,
    currentSession: currentSession || sessions.find(s => s.id === currentSessionId),
    currentSessionId,
    messages,
    isSending,
    loadingSessions,
    tokenCount,
    charCount,
    pendingModelOverride,

    // Actions
    createSession,
    updateSession,
    deleteSession,
    switchSession,
    sendMessage,
    setModelOverride,
    refetchSessions
  }
}
