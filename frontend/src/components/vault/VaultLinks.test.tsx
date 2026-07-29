import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

vi.mock('@/lib/hooks/use-translation', () => ({ useTranslation: () => ({ t: (key: string) => key }) }))

import { VaultLinks } from './VaultLinks'

describe('VaultLinks', () => {
  it('renders a backlink using the source note identity and navigates to that source', () => {
    const onNavigate = vi.fn()
    render(<VaultLinks title="Backlinks" direction="source" unresolvedLabel="Unresolved" onNavigate={onNavigate} links={[{
      id: 'note_link:one', source_note_id: 'note:source', target_note_id: 'note:current',
      target_text: 'Current note', source_note_title: 'Project overview', link_kind: 'wikilink', resolved: true,
      source_start: 0, source_end: 14,
    }]} />)

    fireEvent.click(screen.getByRole('button', { name: 'Project overview' }))
    expect(onNavigate).toHaveBeenCalledWith('note:source')
    expect(screen.queryByRole('button', { name: 'Current note' })).not.toBeInTheDocument()
  })
})
