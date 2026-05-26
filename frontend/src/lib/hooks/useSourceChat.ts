'use client'

import { useState, useCallback, useRef, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { getApiErrorMessage } from '@/lib/utils/error-handler'
import { useTranslation } from '@/lib/hooks/use-translation'
import { sourceChatApi } from '@/lib/api/source-chat'
import {
  SourceChatSession,
  SourceChatMessage,
  SourceChatContextIndicator,
  CreateSourceChatSessionRequest,
  UpdateSourceChatSessionRequest
} from '@/lib/types/api'

export function useSourceChat(sourceId: string) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null)
  const [messages, setMessages] = useState<SourceChatMessage[]>([])
  const [isStreaming, setIsStreaming] = useState(false)
  const [contextIndicators, setContextIndicators] = useState<SourceChatContextIndicator | null>(null)
  const abortControllerRef = useRef<AbortController | null>(null)

  // Fetch sessions
  const { data: sessions = [], isLoading: loadingSessions, refetch: refetchSessions } = useQuery<SourceChatSession[]>({
    queryKey: ['sourceChatSessions', sourceId],
    queryFn: () => sourceChatApi.listSessions(sourceId),
    enabled: !!sourceId
  })

  // Fetch current session with messages
  const { data: currentSession, refetch: refetchCurrentSession } = useQuery({
    queryKey: ['sourceChatSession', sourceId, currentSessionId],
    queryFn: () => sourceChatApi.getSession(sourceId, currentSessionId!),
    enabled: !!sourceId && !!currentSessionId
  })

  // Update messages when session changes
  useEffect(() => {
    if (currentSession?.messages) {
      setMessages(currentSession.messages)
    }
  }, [currentSession])

  // Auto-select most recent session when sessions are loaded
  useEffect(() => {
    if (sessions.length > 0 && !currentSessionId) {
      // Find most recent session (sessions are sorted by created date desc from API)
      const mostRecentSession = sessions[0]
      setCurrentSessionId(mostRecentSession.id)
    }
  }, [sessions, currentSessionId])

  // Create session mutation
  const createSessionMutation = useMutation({
    mutationFn: (data: Omit<CreateSourceChatSessionRequest, 'source_id'>) => 
      sourceChatApi.createSession(sourceId, data),
    onSuccess: (newSession) => {
      queryClient.invalidateQueries({ queryKey: ['sourceChatSessions', sourceId] })
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
    mutationFn: ({ sessionId, data }: { sessionId: string, data: UpdateSourceChatSessionRequest }) =>
      sourceChatApi.updateSession(sourceId, sessionId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['sourceChatSessions', sourceId] })
      queryClient.invalidateQueries({ queryKey: ['sourceChatSession', sourceId, currentSessionId] })
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
      sourceChatApi.deleteSession(sourceId, sessionId),
    onSuccess: (_, deletedId) => {
      queryClient.invalidateQueries({ queryKey: ['sourceChatSessions', sourceId] })
      if (currentSessionId === deletedId) {
        setCurrentSessionId(null)
        setMessages([])
      }
      toast.success(t('chat.sessionDeleted'))
    },
    onError: (err: unknown) => {
      const error = err as { response?: { data?: { detail?: string } }, message?: string };
      toast.error(getApiErrorMessage(error.response?.data?.detail || error.message, (key) => t(key), 'apiErrors.failedToDeleteSession'))
    }
  })

  // Send message with streaming
  const sendMessage = useCallback(async (message: string, modelOverride?: string) => {
    let sessionId = currentSessionId

    // Auto-create session if none exists
    if (!sessionId) {
      try {
        const defaultTitle = message.length > 30 ? `${message.substring(0, 30)}...` : message
        const newSession = await sourceChatApi.createSession(sourceId, { title: defaultTitle })
        sessionId = newSession.id
        setCurrentSessionId(sessionId)
        queryClient.invalidateQueries({ queryKey: ['sourceChatSessions', sourceId] })
      } catch (err: unknown) {
        const error = err as { response?: { data?: { detail?: string } }, message?: string };
        console.error('Failed to create chat session:', error)
        toast.error(getApiErrorMessage(error.response?.data?.detail || error.message, (key) => t(key), 'apiErrors.failedToCreateSession'))
        return
      }
    }

    // v0.7.49 — unique per-send temp id (was `temp-${Date.now()}` which
    // collides on rapid-fire sends and triggered the prefix-filter bug
    // below). Mirrors the v0.7.26 fix on useNotebookChat.
    const tempId = `temp-${(globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random()}`)}`
    const userMessage: SourceChatMessage = {
      id: tempId,
      type: 'human',
      content: message,
      timestamp: new Date().toISOString()
    }
    setMessages(prev => [...prev, userMessage])
    setIsStreaming(true)

    // v0.6.32 — actually wire the AbortController. The previous version
    // declared abortControllerRef but NEVER assigned to .current, so
    // cancelStreaming() was a no-op AND the unmount path leaked the
    // stream reader + setState'd on a dead component.
    abortControllerRef.current?.abort()
    const controller = new AbortController()
    abortControllerRef.current = controller

    // v0.7.49 — stable AI streaming id captured in the closure so the
    // map-update callbacks don't need to read the mutating `aiMessage`
    // object. We also no longer mutate the in-state message in place.
    const streamingAiId = `streaming-${(globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random()}`)}`
    let aiCreated = false
    let aiAccumulated = ''

    let reader: ReadableStreamDefaultReader<Uint8Array> | null = null
    try {
      const response = await sourceChatApi.sendMessage(
        sourceId, sessionId,
        { message, model_override: modelOverride },
        controller.signal,
      )

      if (!response) {
        throw new Error('No response body')
      }

      reader = response.getReader()
      const decoder = new TextDecoder()
      // v0.7.49 — multi-bug fix in this section:
      //   (a) `decoder.decode(value)` must use `{ stream: true }`
      //       so multibyte UTF-8 (CJK, emoji) split across two TCP
      //       chunks doesn't get replaced with U+FFFD. Mirrors the
      //       correct usage in chat.ts:129 and use-ask.ts:106.
      //   (b) lines need a buffer kept across reads — a `data: …\n\n`
      //       frame is regularly split across two TCP chunks, and
      //       `text.split('\n')` without buffering silently drops
      //       events. We now `buffer.split('\n')` with `buffer = lines.pop()`
      //       to carry the trailing partial line forward.
      //   (c) bounded buffer so a pathological stream that never emits
      //       a newline can't grow unbounded.
      let buffer = ''
      const BUFFER_MAX = 4 * 1024 * 1024

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        if (buffer.length > BUFFER_MAX) {
          throw new Error('source-chat stream buffer exceeded 4 MiB')
        }

        const lines = buffer.split('\n')
        buffer = lines.pop() ?? ''  // keep partial last line for next read

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6))

              if (data.type === 'ai_message_delta') {
                // v0.7.42/v0.7.49 — append delta. No object mutation;
                // closure variables only.
                aiAccumulated += data.content || ''
                if (!aiCreated) {
                  const initial: SourceChatMessage = {
                    id: streamingAiId,
                    type: 'ai',
                    content: aiAccumulated,
                    timestamp: new Date().toISOString(),
                  }
                  setMessages(prev => [...prev, initial])
                  aiCreated = true
                } else {
                  setMessages(prev =>
                    prev.map(msg => msg.id === streamingAiId
                      ? { ...msg, content: aiAccumulated }
                      : msg
                    )
                  )
                }
              } else if (data.type === 'ai_message') {
                // Terminal canonical message — replaces accumulator.
                aiAccumulated = data.content || aiAccumulated
                if (!aiCreated) {
                  const initial: SourceChatMessage = {
                    id: streamingAiId,
                    type: 'ai',
                    content: aiAccumulated,
                    timestamp: new Date().toISOString(),
                  }
                  setMessages(prev => [...prev, initial])
                  aiCreated = true
                } else {
                  setMessages(prev =>
                    prev.map(msg => msg.id === streamingAiId
                      ? { ...msg, content: aiAccumulated }
                      : msg
                    )
                  )
                }
              } else if (data.type === 'context_indicators') {
                setContextIndicators(data.data)
              } else if (data.type === 'mcp_tool_calls') {
                // v0.8.17 — mirrors useNotebookChat's handling. Stash
                // the MCP tool-call payloads in the TanStack Query
                // cache keyed by streamingAiId so CitationPill's
                // McpPopoverContent can look them up by messageId.
                // Pre-v0.8.17 v0.8.16 wired the chat graph + SSE
                // event but no client handler stashed the payloads,
                // so source-chat pills always showed the v0.8.10
                // placeholder fallback.
                if (Array.isArray(data.calls) && data.calls.length > 0) {
                  queryClient.setQueryData(
                    ['mcp', 'tool-calls', streamingAiId],
                    data.calls,
                  )
                }
              } else if (data.type === 'error') {
                throw new Error(data.message || 'Stream error')
              }
            } catch (e) {
              if (e instanceof SyntaxError) {
                console.error('Error parsing SSE data:', e)
              } else {
                throw e
              }
            }
          }
        }
      }
    } catch (err: unknown) {
      // AbortError = user clicked Stop OR component unmounted; silent.
      if ((err as { name?: string }).name === 'AbortError') {
        // v0.7.49 — drop ONLY this send's optimistic message + streamed
        // AI placeholder. Was `!msg.id.startsWith('temp-')` which wiped
        // EVERY temp-prefixed message — including the NEW send's
        // optimistic message when a prior in-flight send was aborted
        // by the new send (line 138). The new send would see its own
        // message disappear seconds after submitting. Mirrors v0.7.26
        // fix on useNotebookChat.
        setMessages(prev =>
          prev.filter(msg => msg.id !== tempId && msg.id !== streamingAiId)
        )
        return
      }
      const error = err as { response?: { data?: { detail?: string } }, message?: string };
      console.error('Error sending message:', error)
      toast.error(getApiErrorMessage(error.response?.data?.detail || error.message, (key) => t(key), 'apiErrors.failedToSendMessage'))
      // v0.7.54 — same fix as the AbortError branch above: filter ONLY
      // THIS send's tempId + streamingAiId. The old `startsWith('temp-')`
      // also wiped a concurrent retry's optimistic message because the
      // prefix is shared across sends. Mirrors the v0.7.49 fix on the
      // success-cancel path.
      setMessages(prev =>
        prev.filter(msg => msg.id !== tempId && msg.id !== streamingAiId)
      )
    } finally {
      setIsStreaming(false)
      // v0.7.54 — cancel the reader BEFORE releasing the lock so the
      // underlying HTTP response body is actually torn down. Just
      // releaseLock() leaves the connection open until GC and FastAPI's
      // `is_disconnected()` doesn't fire — the local LLM keeps
      // generating tokens nobody will see. Mirrors v0.7.50 chat.ts.
      if (reader) {
        try {
          await reader.cancel()
        } catch {
          // cancel can throw if the stream is already errored; ignore.
        }
        try {
          reader.releaseLock()
        } catch {
          // Reader may already be released by abort/cancel path; ignore.
        }
      }
      // Clear the controller ref if it's still ours.
      if (abortControllerRef.current === controller) {
        abortControllerRef.current = null
      }
      // Refetch session to get persisted messages
      refetchCurrentSession()
    }
  }, [sourceId, currentSessionId, refetchCurrentSession, queryClient, t])

  // v0.6.32 — abort the in-flight controller on unmount.
  useEffect(() => () => {
    abortControllerRef.current?.abort()
    abortControllerRef.current = null
  }, [])

  // Cancel streaming
  const cancelStreaming = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
      setIsStreaming(false)
    }
  }, [])

  // Switch session
  const switchSession = useCallback((sessionId: string) => {
    setCurrentSessionId(sessionId)
    setContextIndicators(null)
  }, [])

  // Create session
  const createSession = useCallback((data: Omit<CreateSourceChatSessionRequest, 'source_id'>) => {
    return createSessionMutation.mutate(data)
  }, [createSessionMutation])

  // Update session
  const updateSession = useCallback((sessionId: string, data: UpdateSourceChatSessionRequest) => {
    return updateSessionMutation.mutate({ sessionId, data })
  }, [updateSessionMutation])

  // Delete session
  const deleteSession = useCallback((sessionId: string) => {
    return deleteSessionMutation.mutate(sessionId)
  }, [deleteSessionMutation])

  return {
    // State
    sessions,
    currentSession: sessions.find(s => s.id === currentSessionId),
    currentSessionId,
    messages,
    isStreaming,
    contextIndicators,
    loadingSessions,
    
    // Actions
    createSession,
    updateSession,
    deleteSession,
    switchSession,
    sendMessage,
    cancelStreaming,
    refetchSessions
  }
}
