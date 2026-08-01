import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { PodcastStudio } from './PodcastStudio'

describe('PodcastStudio', () => {
  it('keeps an editable editorial brief local until a later confirmation', () => {
    render(<PodcastStudio seedDocumentIds={['knowledge_engine_document:plan']} />)

    fireEvent.change(screen.getByLabelText('Central question'), {
      target: { value: 'What changes after the research is connected?' },
    })
    fireEvent.change(screen.getByLabelText('Audience'), { target: { value: 'expert' } })

    expect(screen.getByLabelText('Central question')).toHaveValue('What changes after the research is connected?')
    expect(screen.getByLabelText('Audience')).toHaveValue('expert')
    expect(screen.getByText('No production job is submitted from this planning surface.')).toBeVisible()
  })

  it('moves outline segments with explicit keyboard-accessible controls', () => {
    render(<PodcastStudio seedDocumentIds={['knowledge_engine_document:plan']} />)

    fireEvent.click(screen.getByRole('button', { name: 'Move Findings earlier' }))

    expect(screen.getByRole('status')).toHaveTextContent('Findings moved to position 1')
    expect(document.activeElement).toBe(screen.getByRole('button', { name: 'Move Findings earlier' }))
  })
})
