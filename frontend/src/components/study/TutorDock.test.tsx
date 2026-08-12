import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import { TutorDock } from './TutorDock'

const invoke = vi.fn()
const cancel = vi.fn()
const retry = vi.fn()
const proposeSyllabus = vi.fn()
const router = vi.hoisted(() => ({ push: vi.fn(), replace: vi.fn() }))
let pending = false
let invocationFailed = false
let invocationError: unknown = null

vi.mock('@/lib/hooks/use-study-assistants', () => ({
  useStudyAssistantInvocation: () => ({
    mutateAsync: invoke,
    cancel,
    retry,
    isPending: pending,
    isError: invocationFailed,
    error: invocationError,
    data: null,
    reset: vi.fn(),
  }),
}))
vi.mock('@/lib/hooks/use-study-plans', () => ({
  useStudyPlan: () => ({ data: { plan_id: 'study_plan:one', version: 7 }, isLoading: false }),
  useProposeStudySyllabus: () => ({ mutateAsync: proposeSyllabus, isPending: false }),
}))
vi.mock('next/navigation', () => ({
  useRouter: () => router,
}))
const ANSWER = {
  schema_version: 1,
  response_id: 'study_assistant_response:one',
  session_id: 'study_assistant_session:one',
  plan_id: 'study_plan:one',
  role: 'source_guide',
  authority: 'ask',
  status: 'completed',
  answer: 'The selected material says this.',
  citations: [{ source_id: 'source:one', locator: 'page:2', quote: 'selected material', title: 'Notes' }],
  proposed_actions: [{ action: 'plan.propose.syllabus', label: 'Apply proposed prerequisite unit', expected_revision: 7, unit_id: null }],
  retrieval_receipt: { source_ids: ['source:one'], citation_count: 1 },
  error_code: null,
  created_at: '2026-08-12T12:00:00Z',
  completed_at: '2026-08-12T12:00:01Z',
} as const

describe('TutorDock', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    pending = false
    invocationFailed = false
    invocationError = null
    invoke.mockResolvedValue(ANSWER)
    router.push.mockReset()
    router.replace.mockReset()
  })

  it('supports keyboard role and mode selection while keeping one source-aware foreground tutor', async () => {
    render(<TutorDock planId="study_plan:one" sourceIds={['source:one']} />)

    const role = screen.getByRole('combobox', { name: 'Tutor role' })
    const mode = screen.getByRole('combobox', { name: 'Tutor mode' })
    fireEvent.change(role, { target: { value: 'source_guide' } })
    fireEvent.change(mode, { target: { value: 'ask_question' } })
    expect(role).toHaveValue('source_guide')
    expect(mode).toHaveValue('ask_question')
    expect(screen.getByText('Source-only')).toBeInTheDocument()
    expect(screen.getAllByRole('region', { name: /Tutor dock/i })).toHaveLength(1)
  })

  it('changes role and mode together using a compatible default mode policy', () => {
    render(<TutorDock planId="study_plan:one" />)

    const role = screen.getByRole('combobox', { name: 'Tutor role' })
    const mode = screen.getByRole('combobox', { name: 'Tutor mode' })

    fireEvent.change(role, { target: { value: 'curriculum_architect' } })
    expect(role).toHaveValue('curriculum_architect')
    expect(mode).toHaveValue('plan_today')

    fireEvent.change(role, { target: { value: 'research_scout' } })
    expect(role).toHaveValue('research_scout')
    expect(mode).toHaveValue('research_gap')
  })

  it('requests web permission explicitly and maps it to an approved scope', async () => {
    render(<TutorDock planId="study_plan:one" approvedNetworkScope={['https://example.edu/']} />)
    fireEvent.change(screen.getByRole('combobox', { name: 'Tutor mode' }), { target: { value: 'research_gap' } })
    fireEvent.click(screen.getByRole('button', { name: 'Request web research permission' }))
    expect(screen.getByText('Web research permission requested for this invocation.')).toBeInTheDocument()
    fireEvent.change(screen.getByRole('textbox', { name: 'Tutor prompt' }), { target: { value: 'Find the missing topic' } })
    fireEvent.click(screen.getByRole('button', { name: 'Ask tutor' }))
    await waitFor(() => expect(invoke).toHaveBeenCalledWith(expect.objectContaining({
      planId: 'study_plan:one',
      role: 'research_scout',
      input: expect.objectContaining({
        request_id: expect.stringMatching(/^study-assistant-request:/),
        model_route: 'cloud',
        network_allowed: true,
        approved_network_scope: ['https://example.edu/'],
      }),
    })))
  })

  it('gives each new submission an explicit bounded request id', async () => {
    render(<TutorDock planId="study_plan:one" />)
    const prompt = screen.getByRole('textbox', { name: 'Tutor prompt' })
    const ask = screen.getByRole('button', { name: 'Ask tutor' })
    fireEvent.change(prompt, { target: { value: 'Explain this once' } })
    fireEvent.click(ask)
    await waitFor(() => expect(invoke).toHaveBeenCalledTimes(1))
    const firstRequestId = invoke.mock.calls[0]?.[0]?.input?.request_id
    expect(firstRequestId).toEqual(expect.stringMatching(/^study-assistant-request:/))
    expect(typeof firstRequestId).toBe('string')
    expect((firstRequestId as string).length).toBeLessThanOrEqual(128)

    fireEvent.change(prompt, { target: { value: 'Explain this again' } })
    fireEvent.click(ask)
    await waitFor(() => expect(invoke).toHaveBeenCalledTimes(2))
    const secondRequestId = invoke.mock.calls[1]?.[0]?.input?.request_id
    expect(secondRequestId).toEqual(expect.stringMatching(/^study-assistant-request:/))
    expect(secondRequestId).not.toBe(firstRequestId)
  })

  it('requires approval before a tutor proposal changes the syllabus', async () => {
    invoke.mockResolvedValueOnce(ANSWER)
    render(<TutorDock planId="study_plan:one" sourceIds={['source:one']} />)
    fireEvent.change(screen.getByRole('textbox', { name: 'Tutor prompt' }), { target: { value: 'Propose a prerequisite' } })
    fireEvent.click(screen.getByRole('button', { name: 'Ask tutor' }))
    await waitFor(() => expect(screen.getByRole('button', { name: 'Apply proposed prerequisite unit' })).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: 'Apply proposed prerequisite unit' }))
    expect(screen.getByRole('dialog', { name: 'Review tutor proposal' })).toBeVisible()
    expect(proposeSyllabus).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Confirm proposal' }))
    await waitFor(() => expect(proposeSyllabus).toHaveBeenCalledWith({ planId: 'study_plan:one', input: { expected_revision: 7 } }))
  })

  it('navigates citations and keeps unsupported actions inert', async () => {
    render(<TutorDock planId="study_plan:one" sourceIds={['source:one']} />)
    fireEvent.change(screen.getByRole('textbox', { name: 'Tutor prompt' }), { target: { value: 'Explain' } })
    fireEvent.click(screen.getByRole('button', { name: 'Ask tutor' }))
    await waitFor(() => expect(screen.getByRole('button', { name: /Notes, page:2/i })).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: /Notes, page:2/i }))
    expect(router.push).toHaveBeenCalledWith('/sources/source%3Aone?locator=page%3A2')
  })

  it('cancels an invocation and exposes a compact drawer with focus return', async () => {
    pending = true
    render(<TutorDock planId="study_plan:one" />)
    fireEvent.change(screen.getByRole('textbox', { name: 'Tutor prompt' }), { target: { value: 'Another request' } })
    expect(screen.getByRole('button', { name: /Tutor is working/i })).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: /Tutor is working/i }))
    expect(invoke).not.toHaveBeenCalled()
    const toggle = screen.getByRole('button', { name: 'Close tutor dock' })
    fireEvent.click(toggle)
    expect(screen.getByRole('button', { name: 'Open tutor dock' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Open tutor dock' }))
    expect(toggle).toHaveFocus()
    fireEvent.click(screen.getByRole('button', { name: 'Cancel tutor invocation' }))
    expect(cancel).toHaveBeenCalledTimes(1)
  })

  it('shows a bounded timeout error and retries the same foreground request', () => {
    invocationFailed = true
    invocationError = { response: { data: { detail: { code: 'assistant_timeout' } } } }
    render(<TutorDock planId="study_plan:one" />)
    expect(screen.getByRole('alert')).toHaveTextContent('timed out')
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }))
    expect(retry).toHaveBeenCalledTimes(1)
  })
})
