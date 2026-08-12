import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { StudyLearningSession } from './StudyLearningSession'

vi.mock('./TutorDock', () => ({
  TutorDock: ({ planId }: { planId: string }) => <div role="region" aria-label="Tutor dock">Tutor dock for {planId}</div>,
}))

describe('StudyLearningSession', () => {
  it('renders one foreground tutor session for the Learn tab', () => {
    render(<StudyLearningSession planId="study_plan:one" sourceIds={['source:one']} />)
    expect(screen.getByRole('heading', { name: 'Learning session' })).toBeInTheDocument()
    expect(screen.getAllByRole('region', { name: 'Tutor dock' })).toHaveLength(1)
  })
})
