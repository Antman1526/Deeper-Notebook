import { act, renderHook } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { studyAssistantsApi } from '@/lib/api/study-assistants'

import {
  useStudyAssistantInvocation,
  type StudyAssistantInvocationVariables,
} from './use-study-assistants'

vi.mock('@/lib/api/study-assistants', () => ({
  studyAssistantsApi: {
    invoke: vi.fn(),
  },
}))

const invoke = vi.mocked(studyAssistantsApi.invoke)

const RESPONSE = {
  schema_version: 1,
  response_id: 'study_assistant_response:one',
  session_id: 'study_assistant_session:one',
  plan_id: 'study_plan:one',
  role: 'source_guide',
  authority: 'ask',
  status: 'completed',
  answer: 'Use the selected source.',
  citations: [],
  proposed_actions: [],
  retrieval_receipt: { source_ids: [], citation_count: 0 },
  error_code: null,
  created_at: '2026-08-12T12:00:00Z',
  completed_at: '2026-08-12T12:00:01Z',
} as const

const VARIABLES: StudyAssistantInvocationVariables = {
  planId: 'study_plan:one',
  role: 'source_guide',
  input: {
    authority: 'ask',
    prompt: 'Explain the selected source',
    selected_source_ids: ['source:one'],
    model_route: 'local',
    network_allowed: false,
    approved_network_scope: [],
    timeout_seconds: 30,
    request_id: 'study-assistant-request:stable-one',
  },
}

describe('useStudyAssistantInvocation', () => {
  beforeEach(() => vi.clearAllMocks())

  it('retries the same explicit request id as the original logical request', async () => {
    invoke.mockRejectedValueOnce(new Error('assistant_timeout')).mockResolvedValueOnce(RESPONSE as never)
    const { result } = renderHook(() => useStudyAssistantInvocation())

    await act(async () => {
      await expect(result.current.mutateAsync(VARIABLES)).rejects.toThrow('assistant_timeout')
    })
    await act(async () => {
      await expect(result.current.retry()).resolves.toEqual(RESPONSE)
    })

    expect(invoke).toHaveBeenCalledTimes(2)
    expect(invoke.mock.calls[0]?.[2].request_id).toBe('study-assistant-request:stable-one')
    expect(invoke.mock.calls[1]?.[2].request_id).toBe('study-assistant-request:stable-one')
  })

  it('keeps the foreground lock until an abort-ignoring transport settles', async () => {
    let resolveOld: ((value: unknown) => void) | undefined
    const oldTransport = new Promise((resolve) => {
      resolveOld = resolve
    })
    invoke.mockReturnValueOnce(oldTransport as never).mockResolvedValueOnce(RESPONSE as never)
    const { result } = renderHook(() => useStudyAssistantInvocation())
    let oldInvocation: Promise<unknown> | undefined

    act(() => {
      oldInvocation = result.current.mutateAsync(VARIABLES)
    })
    act(() => {
      result.current.cancel()
    })

    await act(async () => {
      await expect(result.current.mutateAsync({
        ...VARIABLES,
        input: { ...VARIABLES.input, request_id: 'study-assistant-request:new' },
      })).rejects.toThrow('Tutor invocation already in progress')
    })

    resolveOld?.(RESPONSE)
    await act(async () => {
      await oldInvocation
    })
    expect(invoke).toHaveBeenCalledTimes(1)
  })
})
