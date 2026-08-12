import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { TurnIntoPodcastAction } from './TurnIntoPodcastAction'

const selection = {
  kind: 'knowledge_document' as const,
  documentId: 'knowledge_engine_document:research',
}

describe('TurnIntoPodcastAction', () => {
  it('opens an explicit optional destination without submitting generation', () => {
    const onOpen = vi.fn()
    render(
      <TurnIntoPodcastAction
        selection={selection}
        destination="quick"
        onOpen={onOpen}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Turn into podcast' }))

    expect(onOpen).toHaveBeenCalledOnce()
    expect(onOpen).toHaveBeenCalledWith([selection], 'quick')
    expect(screen.getByRole('button', { name: 'Turn into podcast' })).toHaveClass('min-h-8', 'min-w-8')
  })

  it('keeps an unavailable action visible with its exact reason', () => {
    render(
      <TurnIntoPodcastAction
        selection={selection}
        destination="studio"
        disabledReason="No readable content is available"
        onOpen={vi.fn()}
      />,
    )

    expect(screen.getByRole('button', { name: 'Turn into podcast' })).toBeDisabled()
    expect(screen.getByText('No readable content is available')).toBeVisible()
  })

  it('forwards an explicit multi-selection without starting production', () => {
    const onOpen = vi.fn()
    const selections = [selection, {
      kind: 'knowledge_document' as const,
      documentId: 'knowledge_engine_document:second',
    }]
    render(
      <TurnIntoPodcastAction
        selections={selections}
        destination="studio"
        label="Open in Podcast Studio"
        onOpen={onOpen}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Open in Podcast Studio' }))

    expect(onOpen).toHaveBeenCalledWith(selections, 'studio')
  })
})
