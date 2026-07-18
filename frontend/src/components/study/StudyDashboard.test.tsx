import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { StudyDashboard } from './StudyDashboard'

describe('StudyDashboard', () => {
  it('uses deterministic lapse counts to surface weak source topics', () => {
    render(<StudyDashboard cards={[{
      id: 'study_card:one', artifact_id: 'artifact:research', artifact_card_id: 'one', version: 1,
      front: 'Question', back: 'Answer', citations: [], due: '2026-07-17T00:00:00Z',
      stability: 3, difficulty: 5, lapse_count: 2, current: true,
    }]} />)

    expect(screen.getByText('Due today')).toBeInTheDocument()
    expect(screen.getByText('artifact:research')).toBeInTheDocument()
    expect(screen.getByText('2 lapses')).toBeInTheDocument()
  })
})
