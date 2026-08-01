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
})
