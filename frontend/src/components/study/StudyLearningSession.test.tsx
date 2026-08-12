import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { StudyLearningSession } from './StudyLearningSession'

vi.mock('./TutorDock', () => ({
  TutorDock: ({
    planId,
    voiceTranscript,
    onAssistantAnswer,
  }: {
    planId: string
    voiceTranscript?: { id: number; text: string } | null
    onAssistantAnswer?: (answer: string) => void
  }) => (
    <div role="region" aria-label="Tutor dock">
      <span>Tutor dock for {planId}</span>
      <textarea aria-label="Tutor prompt" value={voiceTranscript?.text ?? ''} readOnly />
      <button type="button" onClick={() => onAssistantAnswer?.('Latest tutor answer')}>Complete answer</button>
      <button type="button" aria-label="Ask tutor">Ask tutor</button>
    </div>
  ),
}))

vi.mock('./StudyVoiceTutor', () => ({
  StudyVoiceTutor: ({
    capability,
    onTranscript,
    assistantText,
  }: {
    capability: { stt: 'ready' | 'unavailable'; tts: 'ready' | 'unavailable' }
    onTranscript?: (transcript: string) => void
    assistantText?: string | null
  }) => (
    <div aria-label="Spoken tutoring">
      <button type="button" disabled={capability.stt !== 'ready'} onClick={() => onTranscript?.('Dictated study question')}>
        Record question
      </button>
      {assistantText ? <button type="button">Play tutor response</button> : null}
    </div>
  ),
}))

const capability = vi.fn()
vi.mock('@/lib/api/study-voice', () => ({
  studyVoiceApi: {
    capability: (...args: unknown[]) => capability(...args),
  },
}))

describe('StudyLearningSession', () => {
  it('composes a ready voice receipt with the text tutor without dispatch or autoplay', async () => {
    capability.mockResolvedValueOnce({ stt: 'ready', tts: 'ready' })
    render(<StudyLearningSession planId="study_plan:one" sourceIds={['source:one']} />)

    const record = await screen.findByRole('button', { name: 'Record question' })
    await waitFor(() => expect(record).toBeEnabled())
    fireEvent.click(record)
    expect(screen.getByRole('textbox', { name: 'Tutor prompt' })).toHaveValue('Dictated study question')
    expect(screen.getByRole('button', { name: 'Ask tutor' })).toBeEnabled()

    fireEvent.click(screen.getByRole('button', { name: 'Complete answer' }))
    expect(await screen.findByRole('button', { name: 'Play tutor response' })).toBeVisible()
    expect(screen.queryByRole('audio')).not.toBeInTheDocument()
  })

  it('keeps the text tutor usable when the capability receipt is unavailable', async () => {
    capability.mockResolvedValueOnce({ stt: 'unavailable', tts: 'unavailable' })
    render(<StudyLearningSession planId="study_plan:two" />)
    expect(await screen.findByRole('button', { name: 'Record question' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Ask tutor' })).toBeEnabled()
    expect(screen.getByRole('textbox', { name: 'Tutor prompt' })).toBeInTheDocument()
  })

  it('renders one foreground tutor session for the Learn tab', () => {
    capability.mockResolvedValue({ stt: 'unavailable', tts: 'unavailable' })
    render(<StudyLearningSession planId="study_plan:one" sourceIds={['source:one']} />)
    expect(screen.getByRole('heading', { name: 'Learning session' })).toBeInTheDocument()
    expect(screen.getAllByRole('region', { name: 'Tutor dock' })).toHaveLength(1)
  })
})
