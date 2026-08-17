// v0.8.97 — ExamLab view-state contract: setup → taking (no answer key) →
// results (full feedback + idempotent seed button).
import React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'

import { ExamLab } from './ExamLab'
import type { ExamAttempt } from '@/lib/api/study-exams'

const mocks = vi.hoisted(() => ({
  attempt: null as ExamAttempt | null,
  startMutate: vi.fn(),
  submitMutate: vi.fn(),
  seedMutate: vi.fn(),
}))

vi.mock('@/lib/hooks/use-study-exams', () => ({
  useExamAttempts: () => ({ data: [] }),
  useExamAttempt: () => ({ data: mocks.attempt }),
  useStartExam: () => ({ mutate: mocks.startMutate, isPending: false, isError: false }),
  useSubmitExam: () => ({ mutate: mocks.submitMutate, isPending: false, isError: false }),
  useSeedExamMisses: () => ({ mutate: mocks.seedMutate, isPending: false }),
}))

vi.mock('@/lib/hooks/use-notebooks', () => ({
  useNotebooks: () => ({ data: [{ id: 'notebook:n1', name: 'Biology' }] }),
}))

vi.mock('@tanstack/react-query', () => ({
  useQuery: () => ({ data: [], isLoading: false }),
}))

vi.mock('@/lib/api/studio', () => ({
  studioApi: { listArtifacts: vi.fn() },
}))

const baseAttempt: ExamAttempt = {
  id: 'study_exam_attempt:t1',
  artifact_id: 'studio_artifact:q1',
  notebook_id: 'notebook:n1',
  title: 'Biology midterm',
  question_count: 2,
  duration_sec: 1200,
  started_at: new Date().toISOString(),
  deadline: new Date(Date.now() + 20 * 60 * 1000).toISOString(),
  submitted_at: null,
  late: null,
  correct_count: null,
  score_percent: null,
  seeded_indices: [],
  questions: [
    {
      index: 0,
      prompt: 'What is a mitochondrion?',
      options: [
        { id: 'a', text: 'The powerhouse of the cell' },
        { id: 'b', text: 'A type of leaf' },
      ],
    },
    {
      index: 1,
      prompt: 'DNA stands for?',
      options: [
        { id: 'a', text: 'Deoxyribonucleic acid' },
        { id: 'b', text: 'Dynamic nucleic array' },
      ],
    },
  ],
  results: null,
}

beforeEach(() => {
  mocks.attempt = null
  mocks.startMutate.mockClear()
  mocks.submitMutate.mockClear()
  mocks.seedMutate.mockClear()
})

describe('ExamLab', () => {
  it('renders setup with notebook picker when no attempt is active', () => {
    render(<ExamLab />)
    expect(screen.getByTestId('examlab-setup')).toBeInTheDocument()
    expect(screen.getByTestId('examlab-notebook-select')).toBeInTheDocument()
    expect(screen.getByTestId('examlab-start')).toBeDisabled()
  })

  it('taking view shows a countdown and questions, and submits picked answers', () => {
    mocks.attempt = baseAttempt
    render(<ExamLab />)
    expect(screen.getByTestId('examlab-taking')).toBeInTheDocument()
    expect(screen.getByTestId('examlab-countdown')).toBeInTheDocument()
    expect(screen.getByText(/What is a mitochondrion/)).toBeInTheDocument()
    // The taking payload carries no answer key or explanations.
    expect(screen.queryByText(/Correct:/)).not.toBeInTheDocument()

    fireEvent.click(screen.getByLabelText('The powerhouse of the cell'))
    fireEvent.click(screen.getByTestId('examlab-submit'))
    expect(mocks.submitMutate).toHaveBeenCalledTimes(1)
    expect(mocks.submitMutate.mock.calls[0][0]).toEqual({
      attemptId: 'study_exam_attempt:t1',
      answers: { '0': 'a' },
    })
  })

  it('grades view renders results, correct answers, and the seed button', () => {
    mocks.attempt = {
      ...baseAttempt,
      submitted_at: new Date().toISOString(),
      late: false,
      correct_count: 1,
      score_percent: 50.0,
      questions: null,
      results: [
        {
          index: 0,
          prompt: 'What is a mitochondrion?',
          options: baseAttempt.questions![0].options,
          correct: true,
          answered: true,
          selected_option_id: 'a',
          correct_option_id: 'a',
          explanation: '',
          citations: [],
        },
        {
          index: 1,
          prompt: 'DNA stands for?',
          options: baseAttempt.questions![1].options,
          correct: false,
          answered: false,
          selected_option_id: null,
          correct_option_id: 'a',
          explanation: 'Deoxyribonucleic acid.',
          citations: [],
        },
      ],
    }
    render(<ExamLabWithActiveAttempt />)
    expect(screen.getByTestId('examlab-results')).toBeInTheDocument()
    expect(screen.getByText(/Biology midterm — 50%/)).toBeInTheDocument()
    expect(screen.getByText('Not answered')).toBeInTheDocument()
    const seed = screen.getByTestId('examlab-seed-misses')
    expect(seed).toHaveTextContent('Add 1 missed to review deck')
    fireEvent.click(seed)
    expect(mocks.seedMutate).toHaveBeenCalledWith('study_exam_attempt:t1')
  })

  it('seed button disables once every miss is seeded', () => {
    mocks.attempt = {
      ...baseAttempt,
      submitted_at: new Date().toISOString(),
      late: false,
      correct_count: 1,
      score_percent: 50.0,
      seeded_indices: [1],
      questions: null,
      results: [
        {
          index: 1,
          prompt: 'DNA stands for?',
          options: baseAttempt.questions![1].options,
          correct: false,
          answered: false,
          selected_option_id: null,
          correct_option_id: 'a',
          explanation: '',
          citations: [],
        },
      ],
    }
    render(<ExamLabWithActiveAttempt />)
    const seed = screen.getByTestId('examlab-seed-misses')
    expect(seed).toBeDisabled()
    expect(seed).toHaveTextContent('Missed questions added to review deck')
  })
})

// The component reads the attempt through useExamAttempt(activeAttemptId),
// which is mocked to return mocks.attempt regardless of id — but the finished/
// taking branches also require activeAttemptId to be non-null... they don't:
// they key on attempt.data alone. This wrapper exists purely for readability.
function ExamLabWithActiveAttempt() {
  return <ExamLab />
}
