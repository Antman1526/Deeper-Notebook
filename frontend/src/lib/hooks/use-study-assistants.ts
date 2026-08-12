'use client'

import { useCallback, useEffect, useRef, useState } from 'react'

import { studyAssistantsApi } from '@/lib/api/study-assistants'
import type {
  StudyAssistantRequest,
  StudyAssistantResponse,
  StudyAssistantRole,
} from '@/lib/types/study-assistants'

export interface StudyAssistantInvocationVariables {
  planId: string
  role: StudyAssistantRole
  input: StudyAssistantRequest
}

interface InvocationState {
  status: 'idle' | 'pending' | 'success' | 'error' | 'cancelled'
  data: StudyAssistantResponse | null
  error: unknown
}

function isAbortError(error: unknown): boolean {
  if (!error || typeof error !== 'object') return false
  const value = error as { name?: unknown; code?: unknown }
  return value.name === 'AbortError' || value.name === 'CanceledError' || value.code === 'ERR_CANCELED'
}

/** One abortable foreground invocation.  The dock owns the only instance. */
export function useStudyAssistantInvocation() {
  const [state, setState] = useState<InvocationState>({ status: 'idle', data: null, error: null })
  const controllerRef = useRef<AbortController | null>(null)
  const activeRef = useRef(false)
  const mountedRef = useRef(true)
  const runIdRef = useRef(0)
  const lastVariablesRef = useRef<StudyAssistantInvocationVariables | null>(null)

  useEffect(() => () => {
    mountedRef.current = false
    controllerRef.current?.abort()
    controllerRef.current = null
    activeRef.current = false
  }, [])

  const mutateAsync = useCallback(async (variables: StudyAssistantInvocationVariables) => {
    if (activeRef.current) throw new Error('Tutor invocation already in progress')
    activeRef.current = true
    lastVariablesRef.current = variables
    const controller = new AbortController()
    controllerRef.current = controller
    const runId = ++runIdRef.current
    if (mountedRef.current) setState({ status: 'pending', data: null, error: null })
    try {
      const data = await studyAssistantsApi.invoke(variables.planId, variables.role, variables.input, controller.signal)
      if (mountedRef.current && runId === runIdRef.current) setState({ status: 'success', data, error: null })
      // A transport may resolve after abort (for example, a provider that does
      // not observe AbortSignal). Never surface that stale response to the
      // dock as the current foreground result.
      return runId === runIdRef.current && !controller.signal.aborted ? data : undefined
    } catch (error) {
      const cancelled = controller.signal.aborted || isAbortError(error)
      if (mountedRef.current && runId === runIdRef.current) {
        setState({ status: cancelled ? 'cancelled' : 'error', data: null, error: cancelled ? null : error })
      }
      if (cancelled) return undefined
      throw error
    } finally {
      // Keep the single-flight lock until this exact transport settles. The
      // run id intentionally changes on cancel to suppress stale state, so it
      // cannot also decide when the transport lock is safe to release.
      if (controllerRef.current === controller) {
        activeRef.current = false
        controllerRef.current = null
      }
    }
  }, [])

  const mutate = useCallback((variables: StudyAssistantInvocationVariables) => {
    void mutateAsync(variables).catch(() => undefined)
  }, [mutateAsync])

  const cancel = useCallback(() => {
    if (!activeRef.current) return
    runIdRef.current += 1
    controllerRef.current?.abort()
    if (mountedRef.current) setState({ status: 'cancelled', data: null, error: null })
  }, [])

  const retry = useCallback(async () => {
    if (!lastVariablesRef.current || activeRef.current) return undefined
    return mutateAsync(lastVariablesRef.current)
  }, [mutateAsync])

  const reset = useCallback(() => {
    if (activeRef.current) return
    if (mountedRef.current) setState({ status: 'idle', data: null, error: null })
  }, [])

  return {
    mutate,
    mutateAsync,
    cancel,
    retry,
    reset,
    data: state.data,
    error: state.error,
    status: state.status,
    isPending: state.status === 'pending',
    isError: state.status === 'error',
    isSuccess: state.status === 'success',
    isCancelled: state.status === 'cancelled',
  }
}
