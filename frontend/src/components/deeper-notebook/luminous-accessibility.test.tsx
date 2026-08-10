import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { FolioPage } from './folio/FolioPage'

describe('Luminous Folio accessibility', () => {
  it('exposes one named main landmark with a single page heading and a keyboard-reachable action', () => {
    render(
      <FolioPage title="Research workspace" eyebrow="Research Core" actions={<button type="button">Create notebook</button>}>
        <section aria-labelledby="working-notes"><h2 id="working-notes">Working notes</h2><p>Local-first research.</p></section>
      </FolioPage>,
    )

    expect(screen.getAllByRole('main')).toHaveLength(1)
    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1)
    expect(screen.getByRole('main', { name: 'Research workspace' })).toContainElement(
      screen.getByRole('button', { name: 'Create notebook' }),
    )
  })
})
