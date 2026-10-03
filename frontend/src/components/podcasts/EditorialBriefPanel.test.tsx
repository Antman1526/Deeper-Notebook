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

    expect(screen.getByLabelText('podcasts.editorialBriefPanel.centralQuestion')).toBeInTheDocument()
    expect(screen.getByLabelText('podcasts.editorialBriefPanel.audience')).toBeInTheDocument()
    expect(screen.getByLabelText('podcasts.editorialBriefPanel.purpose')).toBeInTheDocument()
    expect(screen.getByLabelText('podcasts.editorialBriefPanel.format')).toBeInTheDocument()
    expect(screen.getByLabelText('podcasts.editorialBriefPanel.targetMinutes')).toBeInTheDocument()
    expect(screen.getByLabelText('podcasts.editorialBriefPanel.requiredTakeaway')).toBeInTheDocument()
    expect(screen.getByLabelText('podcasts.editorialBriefPanel.includeUnanswered')).toBeInTheDocument()
    expect(screen.getByLabelText('podcasts.editorialBriefPanel.evidencePolicy')).toHaveValue('strict')
    expect(screen.getByLabelText('podcasts.editorialBriefPanel.episodeProfile')).toBeInTheDocument()
    expect(screen.getByLabelText('podcasts.editorialBriefPanel.speakerProfile')).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('podcasts.editorialBriefPanel.centralQuestion'), { target: { value: 'What changed?' } })
    fireEvent.change(screen.getByLabelText('podcasts.editorialBriefPanel.purpose'), { target: { value: 'compare' } })
    fireEvent.click(screen.getByLabelText('podcasts.editorialBriefPanel.includeUnanswered'))

    expect(onChange).toHaveBeenCalledWith({ centralQuestion: 'What changed?' })
    expect(onChange).toHaveBeenCalledWith({ purpose: 'compare' })
    expect(onChange).toHaveBeenCalledWith({ includeUnansweredQuestions: true })
  })
})
