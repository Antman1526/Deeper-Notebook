import { describe, expect, it, vi, beforeEach } from 'vitest'

import apiClient from './client'
import {
  decodeStudyAssistantResponse,
  studyAssistantsApi,
} from './study-assistants'

vi.mock('./client', () => ({
  default: {
    post: vi.fn(),
  },
}))

const mockPost = vi.mocked(apiClient.post)

const RESPONSE = {
  schema_version: 1,
  response_id: 'study_assistant_response:one',
  session_id: 'study_assistant_session:one',
  plan_id: 'study_plan:one',
  role: 'source_guide',
  authority: 'ask',
  status: 'completed',
  answer: 'Use the selected source.',
  citations: [{ source_id: 'source:one', locator: 'page:2', quote: 'A useful excerpt', title: 'Notes' }],
  proposed_actions: [],
  retrieval_receipt: { source_ids: ['source:one'], citation_count: 1 },
  error_code: null,
  created_at: '2026-08-12T12:00:00Z',
  completed_at: '2026-08-12T12:00:01Z',
} as const

const REQUEST = {
  authority: 'ask' as const,
  prompt: 'Explain the selected source',
  unit_id: 'unit-one',
  selected_source_ids: ['source:one'],
  model_route: 'local' as const,
  network_allowed: false,
  approved_network_scope: [],
  timeout_seconds: 30,
}

describe('studyAssistantsApi', () => {
  beforeEach(() => vi.clearAllMocks())

  it('decodes a strict Task 11 response and rejects an invalid response', () => {
    expect(decodeStudyAssistantResponse(RESPONSE)).toEqual(RESPONSE)
    expect(() => decodeStudyAssistantResponse({ ...RESPONSE, provider_payload: 'secret' })).toThrow(
      'Invalid Study Assistant response',
    )
  })

  it('accepts backend-compatible multiline answer and citation text', () => {
    const multiline = {
      ...RESPONSE,
      answer: 'Use the selected source.\n\nThen compare its claim with the next passage.',
      citations: [{
        source_id: 'source:one',
        locator: 'page:2',
        quote: 'A useful excerpt\ncontinued on the next line',
        title: 'Notes\nchapter two',
      }],
    }

    expect(decodeStudyAssistantResponse(multiline)).toEqual(multiline)
  })

  it('keeps identifiers and action names strict while allowing response prose formatting', () => {
    expect(() => decodeStudyAssistantResponse({ ...RESPONSE, response_id: 'response\nunsafe' })).toThrow(
      'Invalid Study Assistant response',
    )
    expect(() => decodeStudyAssistantResponse({
      ...RESPONSE,
      proposed_actions: [{ action: 'plan\nunsafe', label: 'Visible label', unit_id: null, expected_revision: null }],
    })).toThrow('Invalid Study Assistant response')
  })

  it('posts only explicit authority, model, and network fields', async () => {
    mockPost.mockResolvedValue({ data: RESPONSE } as never)
    const signal = new AbortController().signal

    await expect(studyAssistantsApi.invoke('study_plan:one', 'source_guide', REQUEST, signal)).resolves.toEqual(RESPONSE)
    expect(mockPost).toHaveBeenCalledWith(
      '/study/plans/study_plan%3Aone/assistants/source_guide:invoke',
      REQUEST,
      expect.objectContaining({ signal }),
    )
  })

  it('accepts a bounded multiline prompt with tabs', async () => {
    const prompt = 'Compare the two claims.\n\tStart with the evidence boundary.'
    mockPost.mockResolvedValue({ data: RESPONSE } as never)

    await expect(studyAssistantsApi.invoke('study_plan:one', 'source_guide', {
      ...REQUEST,
      prompt,
    }, new AbortController().signal)).resolves.toEqual(RESPONSE)
    expect(mockPost).toHaveBeenCalledWith(
      '/study/plans/study_plan%3Aone/assistants/source_guide:invoke',
      expect.objectContaining({ prompt }),
      expect.anything(),
    )
  })

  it('fails closed before dispatching malformed authority or web requests', async () => {
    await expect(studyAssistantsApi.invoke('study_plan:one', 'source_guide', {
      ...REQUEST,
      model_route: 'cloud',
      network_allowed: false,
    } as never)).rejects.toThrow('Invalid Study Assistant request')
    await expect(studyAssistantsApi.invoke('study_plan:one', 'research_scout', {
      ...REQUEST,
      network_allowed: true,
      approved_network_scope: [],
    } as never)).rejects.toThrow('Invalid Study Assistant request')
    expect(mockPost).not.toHaveBeenCalled()
  })
})
