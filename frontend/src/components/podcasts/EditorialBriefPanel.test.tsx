import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { EditorialBriefPanel, type EditorialBriefValues } from './EditorialBriefPanel'

const initial: EditorialBriefValues = {
  centralQuestion: '', audience: 'practitioner', purpose: 'explain', format: 'deep_dive',
  targetMinutes: 20, requiredTakeaway: '', includeUnansweredQuestions: false,
  evidencePolicy: 'strict', episodeProfileName: '', speakerProfileName: '',
}

describe('EditorialBriefPanel', () => {
  it('exposes every controlled editorial field and keeps edits local', () => {
    const onChange = vi.fn()
    render(<EditorialBriefPanel value={initial} onChange={onChange} episodeProfiles={['Research']} speakerProfiles={['Local voice']} />)

    expect(screen.getByLabelText('Central question')).toBeInTheDocument()
    expect(screen.getByLabelText('Audience')).toBeInTheDocument()
    expect(screen.getByLabelText('Purpose')).toBeInTheDocument()
    expect(screen.getByLabelText('Format')).toBeInTheDocument()
    expect(screen.getByLabelText('Target minutes')).toBeInTheDocument()
    expect(screen.getByLabelText('Required takeaway')).toBeInTheDocument()
    expect(screen.getByLabelText('Include unanswered questions')).toBeInTheDocument()
    expect(screen.getByLabelText('Evidence policy')).toHaveValue('strict')
    expect(screen.getByLabelText('Episode profile')).toBeInTheDocument()
    expect(screen.getByLabelText('Speaker profile')).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('Central question'), { target: { value: 'What changed?' } })
    fireEvent.change(screen.getByLabelText('Purpose'), { target: { value: 'compare' } })
    fireEvent.click(screen.getByLabelText('Include unanswered questions'))

    expect(onChange).toHaveBeenCalledWith({ centralQuestion: 'What changed?' })
    expect(onChange).toHaveBeenCalledWith({ purpose: 'compare' })
    expect(onChange).toHaveBeenCalledWith({ includeUnansweredQuestions: true })
  })
})
