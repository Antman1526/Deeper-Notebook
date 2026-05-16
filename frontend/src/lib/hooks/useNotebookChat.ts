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

  // v0.7.50 — AbortController for the v0.7.38 streaming send. Was
  // missing — useSourceChat / use-ask both wire one and the streaming
  // path's resource-leak class of bugs (LLM keeps generating after the
  // user navigates away, setState on a dead component) was reintroduced
  // when v0.7.38 added streaming for notebook chat. Mirrors the v0.6.32
  // useSourceChat pattern. mountedRef is declared later (v0.6.24 used
  // it for a separate race guard); we extend its existing cleanup to
  // also abort the streaming controller.
  const abortControllerRef = useRef<AbortController | null>(null)

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
      //
      // v0.7.59 — read sessions from the TanStack cache instead of the
      // outer closure. The closure captured `sessions` at the render
      // where this mutation object was created. If a second delete
      // fires before the first onSuccess runs, both closures still
      // point at the same pre-delete list and the "next" session
      // picked might already be the one being deleted by the in-flight
      // sibling mutation. The cache always reflects the latest
      // server-confirmed truth.
      if (currentSessionId === deletedId) {
        const cached = queryClient.getQueryData<typeof sessions>(
          QUERY_KEYS.notebookChatSessions(notebookId)
        )
        const list = cached ?? sessions
        const next = list.find((s) => s.id !== deletedId)
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

    // v0.7.38 — token-streaming send. Replaces the buffered
    // chatApi.sendMessage with chatApi.streamMessage. While streaming,
    // a placeholder `streaming-${uuid}` AI message is appended and its
    // .content gets concatenated as tokens arrive. The user sees the
    // response build up character by character — critical for local
    // LLMs at 5-30 tok/s where the full response would otherwise be a
    // 15-30s wall of blank.
    const streamingAiId = `streaming-${(globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random()}`)}`

    // v0.7.50 — bind a per-send AbortController. If a previous send is
    // still in flight when this one starts, abort it (the second send
    // wins). On unmount the effect's cleanup also aborts. Threaded
    // through chatApi.streamMessage as the `signal` argument.
    abortControllerRef.current?.abort()
    const controller = new AbortController()
    abortControllerRef.current = controller

    try {
      const built = await buildContext()

      // Append a placeholder AI message we'll mutate as tokens arrive.
      const placeholder: NotebookChatMessage = {
        id: streamingAiId,
        type: 'ai',
        content: '',
        timestamp: new Date().toISOString(),
      }
      setMessages(prev => [...prev, placeholder])

      let canonicalMessages: NotebookChatMessage[] | null = null
      let streamError: string | null = null

      for await (const event of chatApi.streamMessage({
        session_id: sessionId,
        message,
        context: built.context,
        model_override: modelOverride ?? (currentSession?.model_override ?? undefined),
      }, controller.signal)) {
        // v0.7.50 — bail mid-stream if the component unmounted. Avoids
        // setState-on-dead-component warnings + extra setMessages
        // batch updates after the React tree is gone.
        if (!mountedRef.current) break

        if (event.type === 'token') {
          // Append token text to the placeholder AI message in-place.
          setMessages(prev =>
            prev.map(m =>
              m.id === streamingAiId
                ? { ...m, content: m.content + event.content }
                : m,
            ),
          )
        } else if (event.type === 'done') {
          // Server's canonical message list — wins over our streamed
          // buffer (which lacks IDs, timestamps, and any pre-existing
          // messages from the session checkpoint).
          // v0.7.50 — only accept the canonical replacement if it
          // actually has messages. An empty list comes from an outer
          // chain output we couldn't parse (LangGraph state shape
          // variance) and would otherwise WIPE the just-streamed reply.
          if (event.messages && event.messages.length > 0) {
            canonicalMessages = event.messages
          }
        } else if (event.type === 'error') {
          streamError = event.detail
          break
        }
        // 'start' event acknowledged but not surfaced — UI already
        // shows the placeholder.
      }

      if (streamError) {
        // Error path — clean up the streamed placeholder + the user
        // optimistic message; toast the failure.
        setMessages(prev =>
          prev.filter(m => m.id !== streamingAiId && m.id !== tempId),
        )
        toast.error(
          getApiErrorMessage(streamError, (key) => t(key), 'apiErrors.failedToSendMessage'),
        )
      } else if (canonicalMessages) {
        // Replace local streaming buffer with the server's canonical
        // list — same shape as the non-streaming /chat/execute response.
        setMessages(canonicalMessages)
        await refetchCurrentSession()
      } else {
        // Stream ended without an error or a done event — unusual
        // (server bug?). Keep what we have; refetch for safety.
        await refetchCurrentSession()
      }
    } catch (err: unknown) {
      // v0.7.50 — AbortError = user navigated away mid-stream or a
      // second send aborted us. Silent: don't toast (no real failure).
      // Clean up only THIS send's IDs so the new send's optimistic
      // message survives. mountedRef guard prevents setMessages on
      // unmount.
      if ((err as { name?: string }).name === 'AbortError') {
        if (mountedRef.current) {
          setMessages(prev =>
            prev.filter(m => m.id !== tempId && m.id !== streamingAiId),
          )
        }
        return
      }
      const error = err as { response?: { data?: { detail?: string } }; message?: string };
      console.error('Error sending message:', error)
      toast.error(getApiErrorMessage(error.response?.data?.detail || error.message, (key) => t(key), 'apiErrors.failedToSendMessage'))
      // Clean up both the user's optimistic message AND the streaming
      // AI placeholder.
      setMessages(prev =>
        prev.filter(m => m.id !== tempId && m.id !== streamingAiId),
      )
    } finally {
      // v0.7.50 — clear the ref ONLY if it's still pointing at OUR
      // controller. A second concurrent send would have replaced it
      // already; we don't want to null out the live ref.
      if (abortControllerRef.current === controller) {
        abortControllerRef.current = null
      }
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
    return () => {
      mountedRef.current = false
      // v0.7.50 — abort any in-flight streaming send on unmount so the
      // local LLM stops generating and the FastAPI is_disconnected()
      // check fires. Otherwise the worker keeps producing tokens until
      // it finishes the full response.
      abortControllerRef.current?.abort()
    }
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
